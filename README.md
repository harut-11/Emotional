## インストールとセットアップ

プロジェクトをローカル環境で動かすための手順を説明します。

### 前提条件

このプロジェクトを実行するために必要なソフトウェアやツールを記載します。
- パソコン(Windows, macOS)
- Google Chrome
- Visual Studio Code(推奨エディタ) → Visual Studio Codeが未インストールの場合は、[こちら](https://code.visualstudio.com/download)
- Python

### 手順

1.  **リポジトリのクローン**

    ```bash
    git clone [https://github.com/あなたのユーザー名/あなたのリポジトリ名.git](https://github.com/あなたのユーザー名/あなたのリポジトリ名.git)
    cd あなたのリポジトリ名
    ```

2.  **仮想環境の構築**

    仮想環境を作成
    ```bash
    python3 -m venv venv
    ```

    仮想環境に入る
    ```bash
    venv\Scripts\activate
    ```
    
    仮想環境を終了する(作業を終えてVS Codeなどを閉じるときは、以下のコマンドを実行して仮想環境から抜けてください。)
    ```bash
    deactivate
    ```

2.  **Gemini API キーの作成**

    以下のURLからGemini API キーを作成してください。

    [Gemini API キーの作成](https://ai.google.dev/gemini-api/docs?hl=)
3.  **.envファイルの設定**

    `.env.example`を参考に、プロジェクトのルートディレクトリに`.env`ファイルを作成し、APIキーなどの環境変数を設定してください。

    ```
    GEMINI_API_KEY=あなたのGemini APIキー
    ```
4. **X API キーの作成と設定** 

プロジェクトで使用するX (Twitter) APIのキーを作成し、設定します。

1. X Developer Portalにアクセスし、該当アプリを選択し、**「User authentication settings」**セクションを確認します。

2. OAuth 1.0aの認証設定を以下のように設定してください。

3. App permissions: Read and Post Posts and profile information または Read and Post Posts and Direct message（DM機能を使う場合）を選択します。

4. Type of App: Web App, Automated App or Bot (Confidential Client) を選択します。

5. App info にて、Callback URI / Redirect URLに、以下のリダイレクトURLを設定します。

```
http://127.0.0.1:5000/callback/twitter
```

6. Website URLに、https://example.com など（ご自身のウェブサイトURLを設定してください）

7. 設定を保存した後、「Keys and tokens」セクションに移動し、Consumer Keys (API Key & Secret) を生成または確認します。

⚠️ 重要: ここで表示される API Key と API Secret は、次のステップで利用するため、必ず控えておいてください。

5. **.envファイルの設定**
   
`.env.example`を参考に、プロジェクトのルートディレクトリに`.env`ファイルを作成し、APIキーなどの環境変数を設定してください。
```
TWITTER_API_KEY=あなたのConsumer Key (API Key)
TWITTER_API_SECRET=あなたのConsumer Secret (API Secret)
```

6. **必要なパッケージをインストール**

   ```bash
   pip install Flask google-genai Pillow python-dotenv Flask-SQLAlchemy flask-cors tweepy
   ```
   
7.  **アプリケーションの起動**

    以下のコマンドを実行してアプリケーションを起動します。

    ```bash
    python app.py

    ```

---
