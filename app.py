import os
import json
import io
import datetime
import uuid
# flask.session, flask.redirect, url_for, requestが追加
from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
from dotenv import load_dotenv 
from flask_sqlalchemy import SQLAlchemy
from google import genai
from PIL import Image
from flask_cors import CORS
# V2 API Client をインポートするために、Clientを追加
from tweepy import OAuthHandler, API, Client 
from sqlalchemy import func

# --- 設定 ---
# .envファイルをロード
load_dotenv() 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "http://127.0.0.1:5500")

# --- Twitter設定 (要: .envファイルへの追加) ---
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
# 開発環境のデフォルトURL
TWITTER_CALLBACK_URL = os.getenv("TWITTER_CALLBACK_URL", "http://127.0.0.1:5000/callback/twitter") 

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEYが.envファイルまたは環境変数に設定されていません。")

# --- Flask & SQLAlchemy 設定 ---
app = Flask(__name__, static_url_path='/static')
# SQLiteを使用し、インスタンスフォルダにデータベースを作成
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///emotion_archive.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# セッション暗号化のための秘密鍵を設定
app.secret_key = os.getenv("SECRET_KEY", "your_default_secret_key_if_not_set_in_env")

# 画像ファイルの保存先
UPLOAD_FOLDER = 'images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# 画像保存ディレクトリが存在しない場合は作成
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)
CORS(app, resources={r"/*": {"origins": CORS_ORIGIN}})

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = 'gemini-2.5-flash'


# --- データベースモデル ---
class EmotionRecord(db.Model):
    """感情の記録を保持するモデル"""
    id = db.Column(db.Integer, primary_key=True)
    happiness = db.Column(db.Float, nullable=False)
    anger = db.Column(db.Float, nullable=False)
    text_content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=True) # 保存された画像ファイル名
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)

class TwitterAuth(db.Model):
    """Twitter認証情報を保持するモデル (簡略化のために1レコードのみ想定)"""
    id = db.Column(db.Integer, primary_key=True)
    screen_name = db.Column(db.String(50), nullable=False)
    access_token = db.Column(db.String(255), nullable=False)
    access_token_secret = db.Column(db.String(255), nullable=False)
    
    
# アプリケーションコンテキスト内でのDB初期化
with app.app_context():
    db.create_all()


# --- Twitter認証エンドポイント ---
@app.route('/auth/twitter')
def twitter_auth():
    """Twitter認証を開始し、ユーザーを認証URLにリダイレクト"""
    if not TWITTER_API_KEY or not TWITTER_API_SECRET:
        return render_template('error.html', message="Twitter APIキーが設定されていません。")
        
    try:
        # V1.1の認証ハンドラを使用
        auth = OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_CALLBACK_URL)
        redirect_url = auth.get_authorization_url()
        # リクエストトークンをセッションに保存
        session['request_token'] = auth.request_token 
        return redirect(redirect_url)
    except Exception as e:
        print(f"Twitter認証エラー: {e}")
        return render_template('error.html', message="Twitter認証の開始に失敗しました。")

@app.route('/callback/twitter')
def twitter_callback():
    """Twitterからのコールバックを受け取り、アクセストークンを取得・保存"""
    verifier = request.args.get('oauth_verifier')
    if not verifier:
        return render_template('error.html', message="Twitter認証がキャンセルされました。")

    try:
        # 1. 保存されたリクエストトークンを取得
        request_token = session.pop('request_token', None)
        if not request_token:
            return render_template('error.html', message="セッションにリクエストトークンが見つかりません。認証をやり直してください。")
            
        # 2. アクセストークンを取得
        auth = OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
        auth.request_token = request_token
        
        # Access TokenとAccess Token Secretを取得
        token, token_secret = auth.get_access_token(verifier)
        
        # 3. 【修正済み】V1.1 APIを使ってユーザー情報を取得し、screen_nameを取り出す
        # 認証情報を使ってV1.1 APIクライアントを初期化
        auth.set_access_token(token, token_secret)
        api = API(auth, wait_on_rate_limit=True) 
        
        # verify_credentials() で認証済みのユーザー情報を取得
        user = api.verify_credentials()
        screen_name = user.screen_name # ユーザーオブジェクトからscreen_nameを取得

        # 4. DBにトークンを保存（既存レコードがあれば更新）
        auth_record = TwitterAuth.query.first()
        if not auth_record:
            auth_record = TwitterAuth(
                screen_name=screen_name,
                access_token=token,
                access_token_secret=token_secret
            )
            db.session.add(auth_record)
        else:
            auth_record.screen_name = screen_name
            auth_record.access_token = token
            auth_record.access_token_secret = token_secret
            
        db.session.commit()

        return render_template('auth_success.html', screen_name=screen_name)

    except Exception as e:
        print(f"Twitterコールバックエラー: {e}")
        db.session.rollback()
        return render_template('error.html', message=f"Twitter認証情報の保存に失敗しました。{e}")


# --- トップページ（認証状態の確認用） ---
@app.route('/')
def index():
    """index.htmlをレンダリングし、Twitter認証状態を確認"""
    auth_status = TwitterAuth.query.first() is not None
    return render_template('index.html', twitter_authenticated=auth_status)

# --- 画像表示用エンドポイント ---
@app.route('/images/<filename>')
def serve_image(filename):
    """保存された画像ファイルを配信するエンドポイント"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# --- 感情分析・記録・投稿エンドポイント ---
@app.route('/analyze_emotion', methods=['POST'])
def analyze_emotion():
    """
    1. Gemini APIで感情分析
    2. 結果をDBに保存
    3. Twitterに自動投稿（連携されている場合のみ）
    """
    
    # 0. 入力データの取得と処理
    try:
        text_content = request.form.get('textContent', '').strip()
        image_file = request.files.get('file')
        saved_image_path = None
        
        # テキストまたは画像が必須
        if not text_content and not image_file:
            return jsonify({"error": "テキストまたは画像を入力してください。"}), 400
            
        # 画像ファイルがあれば保存
        image_part = None
        if image_file:
            # PIL Imageオブジェクトを作成
            image_data = image_file.read()
            image = Image.open(io.BytesIO(image_data))
            
            # データベースに保存するファイル名を生成
            filename = f"{uuid.uuid4().hex}_{image_file.filename}"
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # 画像をJPEG形式で保存
            image.save(full_path, 'jpeg')
            saved_image_path = filename
            
            # Gemini API用のPartを作成
            image_part = genai.types.Part.from_bytes(
                data=image_data,
                mime_type=image_file.mimetype # 'image/jpeg'など
            )
            
        # 1. Gemini APIに投げるプロンプトとコンテンツリストを作成
        
        # プロンプト定義
        prompt = (
            "あなたは感情分析の専門家です。以下の入力（テキストおよびオプションで画像）を分析し、"
            "「幸福度 (0.0〜10.0)」と「怒りレベル (0.0〜10.0)」の2つの指標で評価してください。"
            "分析結果はJSON形式のみで出力し、他の文章は一切含めないでください。小数点以下1桁までで評価してください。\n"
            "例: {\"happiness\": 8.5, \"anger\": 1.2}\n\n"
            "--- 入力 ---\n"
            f"テキスト: {text_content}"
        )
        
        # APIに渡すコンテンツリスト
        contents = [prompt]
        if image_part:
            contents.append(image_part)
            
        # 2. Gemini APIの呼び出し
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config={"response_mime_type": "application/json"}
        )
        
        # 3. JSONレスポンスのパース
        try:
            # response.text はJSON形式の文字列として取得される
            analysis_data = json.loads(response.text)
            happiness = analysis_data.get('happiness')
            anger = analysis_data.get('anger')
            
            # 値のバリデーション
            if happiness is None or anger is None or not (0.0 <= happiness <= 10.0 and 0.0 <= anger <= 10.0):
                raise ValueError("JSON形式が不正、または値が範囲外です。")
                
        except (json.JSONDecodeError, ValueError) as e:
             # JSONパースまたは値検証エラーの場合
             print(f"APIレスポンスのパースエラー: {e}")
             raise Exception("感情分析結果の形式が不正です。")

        # 4. データベースへの保存
        new_record = EmotionRecord(
            happiness=happiness,
            anger=anger,
            text_content=text_content,
            image_path=saved_image_path
        )
        db.session.add(new_record)
        db.session.commit()
        
        # 5. 【V2 APIを使用】Twitterへの自動投稿処理 
        twitter_post_success = False
        auth_record = TwitterAuth.query.first() # 連携トークンを取得
        
        if auth_record:
            try:
                # 5-1. V2 Clientの初期化
                client_v2 = Client(
                    consumer_key=TWITTER_API_KEY, 
                    consumer_secret=TWITTER_API_SECRET, 
                    access_token=auth_record.access_token, 
                    access_token_secret=auth_record.access_token_secret
                )

                # V1.1 APIクライアントは画像アップロードに必要
                auth = OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
                auth.set_access_token(auth_record.access_token, auth_record.access_token_secret)
                api_v1 = API(auth, wait_on_rate_limit=True) 
                
                # 5-2. 投稿文の作成 (既存コードを流用)
                base_text = f"【感情記録】\n幸福度: {happiness:.1f} / 怒りレベル: {anger:.1f}\n"
                # Twitterの文字数制限（280文字）を考慮してテキストを調整
                hashtag_length = len("\n#感情アーカイブ #GeminiAPI")
                remaining_length = 280 - len(base_text) - hashtag_length - 3 
                
                post_text = base_text + text_content[:remaining_length]
                if len(text_content) > remaining_length:
                    post_text += "..."
                    
                final_post_text = post_text + "\n#感情アーカイブ #GeminiAPI"

                # 5-3. 画像のアップロード (V1.1 APIクライアントを使用)
                media_ids = []
                if saved_image_path and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], saved_image_path)):
                    full_image_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_image_path)
                    
                    # 画像をTwitterにアップロードし、IDを取得
                    media = api_v1.media_upload(full_image_path)
                    media_ids.append(media.media_id)
                
                # 5-4. 投稿実行 - V2 Clientを使用
                client_v2.create_tweet(text=final_post_text, media_ids=media_ids if media_ids else None)
                
                twitter_post_success = True
                print("Twitter（V2 Client）への自動投稿に成功しました。")
                
            except Exception as e:
                # 以前と同じようにエラーを出力
                print(f"Twitter投稿エラー（記録は成功）: {e}") 
        
        # 6. 成功レスポンス
        return jsonify({
            "status": "success",
            "emotion_data": {"happiness": happiness, "anger": anger},
            "record_id": new_record.id,
            "twitter_posted": twitter_post_success 
        })

    except Exception as e:
        print(f"Gemini API呼び出しエラー: {e}")
        # APIエラーの場合でも、念のためDBセッションをロールバックし、保存した画像があれば削除
        db.session.rollback() 
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
            # 🚨 修正: 画像パスをフロントエンドでアクセス可能なURL形式に変換（/images/filename）
            'image_path': f'/images/{record.image_path}' if record.image_path else None, 
            'created_at': record.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    # 認証ステータスも取得
    auth_status = TwitterAuth.query.first() is not None
    
    # 🚨 修正: JSON構造を { "records": [...], "twitter_authenticated": ... } に変更
    return jsonify({
        "records": history,
        "twitter_authenticated": auth_status
    })
    



if __name__ == '__main__':
    # データベースの初期化と作成をアプリ起動時に行う
    with app.app_context():
        db.create_all()
        
    app.run(debug=True)
