import os
import json
import io
import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory 
from dotenv import load_dotenv 
from flask_sqlalchemy import SQLAlchemy
from google import genai
from PIL import Image
from flask_cors import CORS

# --- 設定 ---
# .envファイルをロード
load_dotenv() 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
CORS_ORIGIN = os.getenv("CORS_ORIGIN", "http://127.0.0.1:5500")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEYが.envファイルまたは環境変数に設定されていません。")

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = 'gemini-2.5-flash'

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 

# --- 画像保存フォルダ設定 ---
UPLOAD_FOLDER = 'images'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- データベース設定 ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL", "sqlite:///emotion_archive.db") 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
CORS(app, resources={r"/*": {"origins": CORS_ORIGIN}})


# --- データベースモデルの定義 ---
class EmotionRecord(db.Model):
    """感情記録を保持するデータベースモデル"""
    id = db.Column(db.Integer, primary_key=True)
    happiness = db.Column(db.Integer, nullable=False)
    anger = db.Column(db.Integer, nullable=False)
    text_content = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(255), nullable=True)  # 【追加】画像ファイルパス
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)

# データベースの初期化
with app.app_context():
    db.create_all()

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


# --- 画像配信エンドポイント ---
@app.route(f'/{UPLOAD_FOLDER}/<filename>', methods=['GET'])
def uploaded_file(filename):
    """保存された画像ファイルをブラウザに配信するエンドポイント"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# --- 感情分析エンドポイント ---
@app.route('/analyze_emotion', methods=['POST'])
def analyze_emotion():
    """テキストと画像をGemini APIに送信し、感情分析結果をDBに保存するAPI"""
    
    text_content = request.form.get('textContent', '')
    image_file = request.files.get('file')

    if not text_content and not image_file:
        return jsonify({"error": "感情分析にはテキストまたは画像が必要です。"}), 400

    contents = []
    saved_image_path = None 
    
  
    if image_file:
        try:
            
            # 1. 画像の処理と保存
            image_bytes = io.BytesIO(image_file.read())
            img = Image.open(image_bytes)
            contents.append(img)

            # 画像の保存
            filename = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}_{image_file.filename}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # 保存のため、ファイルポインタをリセットし、再度開いて保存
            image_file.seek(0)
            img_to_save = Image.open(image_file.stream)
            img_to_save.save(save_path)
            
            # データベースにはファイル名のみを保存
            saved_image_path = filename 

        except Exception as e:
            print(f"画像処理または保存エラー: {e}")
            # エラー発生時のロールバック処理を強化
            if os.path.exists(save_path):
                os.remove(save_path)
            return jsonify({"error": "アップロードされた画像ファイルを処理または保存できませんでした。"}), 500

    # 2. プロンプトとテキストコンテンツ
    system_prompt = (
        "あなたは感情分析の専門家です。提供されたテキストと画像を総合的に分析し、"
        "その内容が示す感情を2つの指標で数値化してください。結果は必ずJSON形式で出力してください。\n"
        "1. happiness (幸福度): -10（非常に不幸）から +10（非常に幸福）の整数値。\n"
        "2. anger (怒りレベル): 0（全く怒っていない）から 10（激しく怒っている）の整数値。\n"
        "JSON形式の例: {\"happiness\": 8, \"anger\": 1}"
    )

    user_prompt = f"分析対象のコンテンツ：\nテキスト: 『{text_content}』"
    
    contents.append(user_prompt)

    try:
        # Gemini APIの呼び出し
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
            }
        )
        
        # JSONレスポンスのパース
        response_text = response.text.strip()
        emotion_data = json.loads(response_text)
        
        # スコアの検証と正規化
        happiness = max(-10, min(10, int(emotion_data.get('happiness', 0))))
        anger = max(0, min(10, int(emotion_data.get('anger', 0))))
        
        # 3. データベースに結果を保存 
        new_record = EmotionRecord(
            happiness=happiness,
            anger=anger,
            text_content=text_content,
            image_path=saved_image_path 
        )
        db.session.add(new_record)
        db.session.commit()
        
        return jsonify({
            "status": "success",
            "emotion_data": {"happiness": happiness, "anger": anger},
            "record_id": new_record.id 
        })

    except Exception as e:
        print(f"Gemini API呼び出しエラー: {e}")
        # APIエラーの場合でも、念のためDBセッションをロールバックし、保存した画像があれば削除
        db.session.rollback() 
        if saved_image_path and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], saved_image_path)):
             os.remove(os.path.join(app.config['UPLOAD_FOLDER'], saved_image_path))
        return jsonify({"error": "感情分析中にエラーが発生しました。入力内容を確認してください。"}), 500


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
            'image_path': record.image_path, 
            'created_at': record.created_at.isoformat() 
        })
        
    return jsonify({
        "status": "success",
        "data": history
    })

# --- アプリケーション起動 ---
if __name__ == '__main__':

    with app.app_context():

        pass 
    app.run(debug=True)