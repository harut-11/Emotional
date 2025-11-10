
import os
import json
import io
import datetime
import uuid
from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
from dotenv import load_dotenv 
from flask_sqlalchemy import SQLAlchemy
from google import genai
from PIL import Image
from flask_cors import CORS
from tweepy import OAuthHandler, API, Client # Clientをv2用に追加
from sqlalchemy import func

# --- 設定 ---
# .envファイルをロード
load_dotenv() 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "http://127.0.0.1:5500")

# --- Twitter設定 ---
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
# 開発環境のデフォルトURL
TWITTER_CALLBACK_URL = os.getenv("TWITTER_CALLBACK_URL", "http://127.0.0.1:5000/callback/twitter") 

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEYが.envファイルまたは環境変数に設定されていません。")

# --- FlaskとSQLAlchemy 設定 ---
app = Flask(__name__, static_url_path='/static')
# SQLiteを使用し、インスタンスフォルダにデータベースを作成
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///emotion_archive.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# セッション暗号化のための秘密鍵
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "your_secret_key_if_not_set")

# ファイルアップロード設定
UPLOAD_FOLDER = 'uploads/images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)
CORS(app, resources={r"/*": {"origins": [CORS_ORIGIN, "http://127.0.0.1:5000"]}})

# --- Gemini API クライアント初期化 ---
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# --- DBモデル定義 ---
class EmotionRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text_content = db.Column(db.String(500), nullable=False)
    happiness = db.Column(db.Float, nullable=False)
    anger = db.Column(db.Float, nullable=False)
    image_path = db.Column(db.String(255), nullable=True) # 保存された画像ファイル名
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)

# アプリケーションコンテキスト内でデータベースを初期化
with app.app_context():
    db.create_all()

# --- Twitter認証関連 ---

def get_twitter_auth_client():
    """OAuth1クライアントを取得 (v1.1 API用)"""
    auth = OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
    if 'request_token' in session:
        auth.request_token = session['request_token']
    return auth

def get_twitter_v2_client():
    """OAuth2 (v2 API) クライアントを取得 (ツイート投稿用)"""
    if 'access_token' in session and 'access_token_secret' in session:
        # v1.1のAuthHandlerのトークンを使用してv2クライアントに認証情報を渡す
        return Client(
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_SECRET,
            access_token=session['access_token'],
            access_token_secret=session['access_token_secret'],
            wait_on_rate_limit=True # レート制限時に待機するオプションを追加
        )
    return None

@app.route('/auth/twitter')
def twitter_auth():
    """Twitter認証を開始"""
    try:
        auth = get_twitter_auth_client()
        redirect_url = auth.get_authorization_url(TWITTER_CALLBACK_URL)
        session['request_token'] = auth.request_token
        return redirect(redirect_url)
    except Exception as e:
        return render_template('error.html', message=f"Twitter認証エラー: {e}")

@app.route('/callback/twitter')
def twitter_callback():
    """Twitter認証コールバック"""
    try:
        verifier = request.args.get('oauth_verifier')
        auth = get_twitter_auth_client()
        token = auth.get_access_token(verifier)
        
        # アクセストークンとシークレットをセッションに保存
        session['access_token'] = token[0]
        session['access_token_secret'] = token[1]
        
        # ユーザー情報を取得 (API v1.1を使用)
        auth.set_access_token(token[0], token[1])
        api = API(auth)
        user = api.verify_credentials()
        session['screen_name'] = user.screen_name
        
        # request_tokenを削除
        session.pop('request_token', None)

        return render_template('auth_success.html', screen_name=user.screen_name)
    except Exception as e:
        session.pop('request_token', None)
        return render_template('error.html', message=f"Twitter認証コールバックエラー: {e}")

@app.route('/twitter_status', methods=['GET'])
def twitter_status():
    """Twitter連携状態をチェック"""
    return jsonify({
        'status': 'linked' if 'access_token' in session else 'unlinked',
        'screen_name': session.get('screen_name')
    })


# --- 感情分析＆記録エンドポイント ---
def post_to_twitter(text, happiness, anger, image_file=None):
    """Twitterに投稿するヘルパー関数 (v1.1でメディアアップロード、v2でツイート)"""
    if 'access_token' not in session:
        return False
    
    try:
        # 投稿メッセージを作成
        message = f"{text}\n\n#感情アーカイブ\nポジティブ: {happiness:.1f}/10.0, ネガティブ: {anger:.1f}/10.0"

        
        auth = get_twitter_auth_client()
        auth.set_access_token(session['access_token'], session['access_token_secret'])
        api_v1 = API(auth) 

        media_ids = None
        if image_file:
            
            media = api_v1.media_upload(image_file)
            media_ids = [media.media_id_string] 

        # --- v2 API でツイートを投稿 ---
        client_v2 = get_twitter_v2_client()
        if not client_v2:
            raise Exception("Twitter V2クライアントの初期化に失敗しました。")

        # ツイート 
        client_v2.create_tweet(text=message, media_ids=media_ids)
        return True
    except Exception as e:
        print(f"Twitter投稿エラー: {e}")
        return False

@app.route('/analyze_emotion', methods=['POST'])
def analyze_emotion():
    """テキストと画像をGeminiで分析し、感情をDBに記録するAPI"""
    
    text_content = request.form.get('text_content', '')
    image_file = request.files.get('file')
    should_post_to_twitter = request.form.get('post_to_twitter', 'false').lower() == 'true'
    if not text_content and not image_file:
        return jsonify({"error": "テキストまたは画像が必要です。"}, 400)

    # 1. 画像の保存処理
    saved_image_path = None
    save_path = None
    if image_file:
        # ファイル名をUUIDで安全に生成
        ext = image_file.filename.split('.')[-1]
        if ext.lower() not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
             return jsonify({"error": "サポートされていない画像形式です。"}, 400)
             
        filename = f"{uuid.uuid4()}.{ext}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image_file.save(save_path)
        saved_image_path = filename

    # 2. Gemini APIのプロンプトとコンテンツリストの準備
    prompt = (
        "あなたは、人間の感情を深く理解する心理分析の専門家です。\n"
        "提供されたテキストと画像を総合的に分析し、書き手の「幸福度（happiness）」と「怒り（anger）」のレベルを0.0から10.0の範囲（浮動小数点数）で正確に評価してください。\n"
        "\n"
        "【重要】分析の指針:\n"
        "1.  **感情の定義:**\n"
        "    * **幸福度 (happiness):** 表面的な喜びだけでなく、満足感、達成感、安らぎ、感謝、穏やかな気持ち、ワクワクする期待感も「幸福度」として評価してください。\n"
        "    * **怒り (anger):** 激しい憤りだけでなく、イライラ、不満、失望、焦燥感、不快感、理不尽さへの抵抗も「怒り」として評価してください。\n"
        "2.  **総合的なコンテキスト分析:**\n"
        "    * テキストと画像の両方が存在する場合、それらの**関連性**を最重要視してください。\n"
        "    * **[補完]:** 画像がテキストの意味を強めている場合（例: テキスト「最高の一日」＋画像「笑顔」）は、スコアを強めてください。\n"
        "    * **[矛盾・皮肉]:** テキストと画像が矛盾する場合（例: テキスト「もう最悪」＋画像「満面の笑み」）は、皮肉（サーカズム）や強がりの可能性を考慮し、隠された本心を推測してください。この場合、テキストの内容をやや優先しつつも、画像の表情が示す複雑さをスコアに反映させてください。\n"
        "    * **[背景の考慮]:** 画像に写る背景、物、状況（例: 散らかった部屋、美しい風景、食事）も、書き手の感情状態を示す重要な手がかりとして分析に含めてください。\n"
        "3.  **ニュアンスの読解:**\n"
        "    * テキストの表面的な単語だけでなく、文脈全体から**暗黙的な感情（implicit meaning）**を読み取ってください。\n"
        "    * 画像が提供されていない場合、またはテキストが提供されていない場合は、提供された片方の情報のみから最大限深く分析してください。\n"
        "\n"
        "--- 出力形式 ---\n"
        "{\n"
        "* 分析結果は、以下のJSONスキーマに厳密に従って出力してください。\n"
        "* スコアは必ず小数点第一位までの数値（float）にしてください。\n"
        "}\n\n"
        "--- 入力情報 ---\n"
        f"テキスト: {text_content}"
    )

    contents = [prompt]
    if save_path:
        try:
            img = Image.open(save_path)
            contents.append(img)
        except Exception as e:
            print(f"PIL画像読み込みエラー: {e}")
            return jsonify({"error": "画像の読み込みに失敗しました。"}, 500)

    try:
        # 3. Gemini API呼び出し
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config={"response_mime_type": "application/json"}
        )
        
        # 4. 感情値の抽出とバリデーション
        emotion_data = json.loads(response.text)
        happiness = float(emotion_data.get('happiness', 0.0))
        anger = float(emotion_data.get('anger', 0.0))
        
        # 値の範囲を0.0から10.0にクリップ
        happiness = max(0.0, min(10.0, happiness))
        anger = max(0.0, min(10.0, anger))
        
        # 5. DBへの保存
        new_record = EmotionRecord(
            text_content=text_content,
            happiness=happiness,
            anger=anger,
            image_path=saved_image_path
        )
        db.session.add(new_record)
        db.session.commit()

        # 6. Twitterへの自動投稿
        twitter_post_success = False
        if 'access_token' in session and should_post_to_twitter:
            # post_to_twitterにファイルの保存パスを渡す
            twitter_post_success = post_to_twitter(text_content, happiness, anger, save_path if saved_image_path else None)
        
        return jsonify({
            "status": "success",
            "happiness": happiness,
            "anger": anger,
            "record_id": new_record.id,
            "twitter_posted": twitter_post_success 
        })

    except Exception as e:
        print(f"Gemini API呼び出しエラー: {e}")
        
        db.session.rollback() 
        # エラー発生時は保存した画像ファイルを削除
        if saved_image_path and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], saved_image_path)):
             os.remove(os.path.join(app.config['UPLOAD_FOLDER'], saved_image_path))
        return jsonify({"error": "感情分析中にエラーが発生しました。入力内容を確認してください。またはTwitter APIキーを確認してください。"}, 500)


# --- データ取得エンドポイント ---
@app.route('/emotion_history', methods=['GET'])
def get_emotion_history():
    """データベースに保存されている全ての感情履歴を取得するAPI"""

    records = EmotionRecord.query.order_by(EmotionRecord.created_at.asc()).all()
    
    history = []
    for record in records:
        history.append({
            'id': record.id,
            'happiness': record.happiness,
            'anger': record.anger,
            'text_content': record.text_content,
            'image_path': f'/images/{record.image_path}' if record.image_path else None, 
            'created_at': record.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    return jsonify({"history": history})


# --- 感情予測エンドポイント ---
@app.route('/predict_emotion', methods=['GET'])
def predict_emotion():
    """
    過去の感情履歴に基づき、Gemini APIで未来の感情傾向とアドバイスを予測する
    """
    # 1. 過去の感情データを取得 (直近30件)
    # 時系列分析に適した形式でデータを取得
    records = EmotionRecord.query.order_by(EmotionRecord.created_at.desc()).limit(30).all()
    
    if not records:
        return jsonify({"error": "予測に必要な感情データが不足しています（最低1件必要）。"}), 400

    # データをJSON形式に変換（予測に必要なデータのみ抽出）
    history_data = []
    # 取得した順序が降順なので、時系列順（昇順）に戻す
    for record in reversed(records):
        history_data.append({
            'date': record.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'happiness': record.happiness,
            'anger': record.anger
        })

    history_json = json.dumps(history_data, ensure_ascii=False)

    # 2. Gemini API用のプロンプトを作成
    prompt = (
        "あなたは、時系列データと人間の感情パターンを分析するプロのデータサイエンティスト兼心理カウンセラーです。\n"
        "提供された過去の感情履歴データ（JSON形式）を分析し、**今後3日以内**に予測されるユーザーの「感情の天気予報」をJSON形式で出力してください。\n"
        "\n"
        "【重要】分析の指針:\n"
        "1.  **傾向の特定:** 過去データの「ポジティブ」と「ネガティブ」の推移から、周期性（例: 週末に幸福度が上がる）、最近の傾向（例: 怒りが上昇傾向）、特定のイベント（例: 怒りが急上昇した日）を特定してください。\n"
        "2.  **根拠のある予測:** 特定した傾向に基づき、今後3日以内（データ最終日の翌日以降）の感情の**平均的な状態**を予測してください。予測スコアは0.0から10.0の範囲（浮動小数点数）とします。\n"
        "3.  **具体的かつ実行可能なアドバイス:** 予測結果に基づき、ユーザーがより良い感情状態で過ごすための、**具体的で実行可能（actionable）**なアドバイスを**2〜3個**提案してください。（例: 「怒りが高まりそうなので、深呼吸する時間を作ってください」「幸福度が高い傾向なので、新しいことに挑戦してみましょう」など）\n"
        "4.  **サマリーの記述:** 予測の**根拠となった傾向**（なぜその予測になったのか）を「tendency_summary」として簡潔に説明してください。\n"
        "\n"
        "--- 出力形式例 ---\n"
        "{\n"
        "  \"prediction_date\": \"今日の日付から約3日後の予測日付（例: 2025-10-17）\",\n"
        "  \"predicted_happiness\": 7.2, \n"
        "  \"predicted_anger\": 1.5, \n"
        "  \"tendency_summary\": \"過去のデータから、幸福度は安定傾向にありますが、3日後あたりで若干の怒りレベルの上昇が見られます。\",\n"
        "  \"advice\": [\n"
        "    \"(例: 予測される怒りレベルの上昇に備え、3日後は無理をせず休息日を設けてください。)\",\n"
        "    \"（例: 幸福度を維持するために、散歩や趣味の時間を取り入れ、ストレス発散を心がけてください。)\"\n"
        "  ]\n"
        "}\n\n"
        "--- 過去の感情データ ---\n"
        f"{history_json}"
    )

    # 3. Gemini APIの呼び出し
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt],
            config={"response_mime_type": "application/json"}
        )

        # 4. JSONレスポンスのパース
        prediction_data = json.loads(response.text)
        
        # 簡易的なバリデーション
        if not all(k in prediction_data for k in ["predicted_happiness", "predicted_anger", "tendency_summary", "advice"]):
            raise ValueError("Geminiからの予測結果のJSON形式が期待通りではありません。")

        return jsonify({
            "status": "success",
            "prediction": prediction_data
        })

    except Exception as e:
        print(f"感情予測エラー: {e}")
        return jsonify({"error": f"感情予測中にエラーが発生しました。データが不足しているか、API設定を確認してください: {e}"}), 500

# --- ルーティング ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/images/<path:filename>')
def serve_image(filename):
    """アップロードされた画像を返す"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Twitter連携状態チェックAPI ---
@app.route("/auth/status")
def auth_status():
    """フロントエンドから呼び出されるTwitter認証状態チェック"""
    if 'access_token' in session and 'screen_name' in session:
        return jsonify({
            "authenticated": True,
            "screen_name": session["screen_name"]
        })
    else:
        return jsonify({"authenticated": False})


if __name__ == '__main__':
    # データベースの初期化
    with app.app_context():
        db.create_all()
    app.run(debug=True)
    

if __name__ == '__main__':
    import threading
    import webbrowser

    port = 5000
    url = f"http://127.0.0.1:{port}"

    # Flaskが起動した直後にブラウザを開く（別スレッドで実行）
    threading.Timer(1.0, lambda: webbrowser.open_new(url)).start()

    # データベースの初期化
    with app.app_context():
        db.create_all()

    app.run(debug=True, port=port)
