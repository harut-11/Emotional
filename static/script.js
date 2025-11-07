const API_HISTORY_URL = '/emotion_history'; // 履歴取得API
const API_ANALYZE_URL = '/analyze_emotion'; // 分析・記録API
const API_PREDICT_URL = '/predict_emotion'; // 感情予測API 

const emotionForm = document.getElementById('emotionForm');     
const submitButton = document.getElementById('submitButton');     
const messageArea = document.getElementById('messageArea'); 
const historyList = document.getElementById('historyList'); 
const tabButtons = document.querySelectorAll('.tabButton');   
const noHistoryMessage = document.getElementById('noHistoryMessage'); 
// 予測結果を表示するコンテナのDOM要素を定義
const emotionPredictionContainer = document.getElementById('emotionPredictionContainer');
const predictionResultDiv = document.getElementById('predictionResult');
// トグルスイッチのDOM要素を取得 
const postToTwitterToggle = document.getElementById('postToTwitterToggle'); 
const textarea = document.getElementById('textContent');
const count = document.getElementById('count');
// Twitterの文字数制限
const TWITTER_MAX_LENGTH = 115;
const maxCountNode = count.parentElement.lastChild;
// ドロップゾーンとファイル入力要素を取得
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('fileInput');
const imagePreviewContainer = document.getElementById('imagePreviewContainer');
const howToUseBtn = document.getElementById('howToUseBtn');
const howToUseModal = document.getElementById('howToUseModal');
const closeHowToUseModalBtn = document.getElementById('closeHowToUseModalBtn');

let composing = false;
// グローバルなチャートインスタンスを保持するための変数
let emotionChartInstance = null; 

textarea.addEventListener('compositionstart', () => composing = true);
textarea.addEventListener('compositionend', () => { composing = false; limit(); });
textarea.addEventListener('input', () => { if (!composing) limit(); });
postToTwitterToggle.addEventListener('change', limit);
limit();

/**
 * メッセージエリアにフィードバックを表示する関数
 * @param {string} type  
 * @param {string} message 
 */
function showMessage(type, message) {
    messageArea.textContent = message;
    messageArea.className = `message-area ${type}`;
}

/**
 * フォームの送信状態を設定する関数
 * @param {boolean} isSubmitting
 */
function setFormSubmitting(isSubmitting) {
    submitButton.disabled = isSubmitting;
    submitButton.textContent = isSubmitting ? '分析中...' : '感情を分析して記録する';
}

/**
 * フォームの状態をリセットする関数
 */
function resetFormState() {
    setFormSubmitting(false);
}
function limit() {
    const isTwitterPostEnabled = postToTwitterToggle.checked;
    const currentLength = textarea.value.length;

    if (isTwitterPostEnabled) {

        textarea.placeholder = '今日の出来事や気分をテキストで記録（例：今日は寝坊した）※115文字以内';
        // Twitter投稿がONの場合 (制限あり) 
        textarea.setAttribute('maxlength', TWITTER_MAX_LENGTH); 
        
        if (currentLength > TWITTER_MAX_LENGTH) {
            // 制限文字数を超えた場合、末尾をカット
            const beforePos = textarea.selectionStart;
            textarea.value = textarea.value.slice(0, TWITTER_MAX_LENGTH);
            // カット後のカーソル位置を調整
            const newPos = Math.min(beforePos, textarea.value.length);
            textarea.setSelectionRange(newPos, newPos);
        }
        
        // カウンター表示を更新 
        count.textContent = textarea.value.length; 
        maxCountNode.textContent = `/${TWITTER_MAX_LENGTH}`; 

    } else {

        textarea.placeholder = '今日の出来事や気分をテキストで記録（例：今日は寝坊した）';
        // Twitter投稿がOFFの場合 (制限なし) 
        textarea.removeAttribute('maxlength'); 
        // カウンター表示を更新 
        count.textContent = currentLength;
        maxCountNode.textContent = ''; // 最大文字数の表示 
    }
}

/**
 * 選択されたファイルのプレビューを表示します
 * @param {FileList} files - fileInputから取得したFileList
 */
function displayImagePreview(files) {
    // 既存のプレビューをクリア
    imagePreviewContainer.innerHTML = '';
    
    if (files && files.length > 0) {
        // 最初のファイル（画像）のみを処理
        const file = files[0];
        
        // ファイルが画像であるか確認
        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            
            reader.onload = function(e) {
                // img要素を作成
                const img = document.createElement('img');
                img.src = e.target.result;
                img.alt = '添付画像のプレビュー';
                img.className = 'image-preview'; // スタイル適用のためクラスを設定
                
                // プレビューコンテナに追加
                imagePreviewContainer.appendChild(img);
                
                // ドロップメッセージを非表示にする
                document.querySelector('.drop-message').style.display = 'none';
            };
            
            // ファイルを読み込み、Data URLとして結果を返します
            reader.readAsDataURL(file);
        } else {
            // 画像以外のファイルが選択された場合の処理（必要に応じて）
            // 例: メッセージ表示をクリア
            showMessage('message-area', '');
        }
    } else {
        // ファイルがない場合はドロップメッセージを表示
        document.querySelector('.drop-message').style.display = 'inline-block';
    }
}

/**
 * 感情データをバックエンドAPIから取得する関数
 * @returns {Promise<Array>} 感情レコードの配列
 */
async function fetchEmotionData() {
    try {
        const response = await fetch(API_HISTORY_URL);
        if (!response.ok) {
            throw new Error('感情履歴の取得に失敗しました。');
        }
        const data = await response.json();
        return data.history || [];
    } catch (error) {
        console.error("データ取得エラー:", error);
        showMessage('error', `感情履歴の取得中にエラーが発生しました: ${error.message}`);
        return [];
    }
}

/**
 * 感情履歴を元に折れ線グラフを描画する関数
 * @param {Array} records 感情レコードの配列
 */
function drawEmotionChart(records) {
    // 既存のチャートがあれば破棄
    if (emotionChartInstance) {
        emotionChartInstance.destroy();
    }

    // データを時系列順に並べ替える
    records.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    
    // --- グラフ表示を改善するための新しいラベル生成ロジック ---
    let lastDate = null; 
    const improvedLabels = records.map(record => {
        const date = new Date(record.created_at);
        const currentDate = `${date.getMonth() + 1}/${date.getDate()}`; // MM/DD形式
        const time = `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;

        let label;
        if (currentDate !== lastDate) {
            // 日付が変わった、または最初のデータの場合、日付と時刻を表示
            label = `${currentDate} ${time}`;
            lastDate = currentDate;
        } else {
            // 同じ日付の場合、時刻のみを表示
            label = time;
        }
        return label;
    });

    const happinessData = records.map(record => record.happiness);
    const angerData = records.map(record => record.anger);

    const ctx = document.getElementById('emotionChart').getContext('2d');
    
    emotionChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
          
            labels: improvedLabels,
            datasets: [
                {
                    label: 'ポジティブ',
                    data: happinessData,
                    borderColor: 'rgb(52, 152, 219)', 
                    backgroundColor: 'rgba(52, 152, 219, 0.2)',
                    fill: false,
                    tension: 0.1,
                    pointRadius: 5, // ポイントを大きく
                    pointHoverRadius: 7
                },
                {
                    label: 'ネガティブ',
                    data: angerData,
                    borderColor: 'rgb(231, 76, 60)', 
                    backgroundColor: 'rgba(231, 76, 60, 0.2)',
                    fill: false,
                    tension: 0.1,
                    pointRadius: 5, // ポイントを大きく
                    pointHoverRadius: 7
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 10,
                    title: {
                        display: true,
                        text: '感情レベル (0-10)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: '日時'
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                },
                title: {
                    display: true,
                    text: '感情の推移'
                }
            }
        }
    });
}


// --- 感情予測処理 ---
async function fetchEmotionPrediction() {
    // 予測メッセージとローディングスピナーの表示
    predictionResultDiv.innerHTML = `
        <p class="auth-message">
            <span class="spinner"></span> <strong>感情の天気予報を分析中...</strong> 過去の傾向から未来を読んでいます。
        </p>
    `;

    try {
        const response = await fetch(API_PREDICT_URL);
        const result = await response.json();

        if (response.ok && result.status === 'success') {
            displayPredictionResult(result.prediction);
        } else {
            // API側でエラーが返された場合（例：データ不足）
            throw new Error(result.error || '予測の取得に失敗しました。');
        }

    } catch (error) {
        console.error("感情予測エラー:", error);
        predictionResultDiv.innerHTML = `
            <p class="auth-message error">
                予測エラー: ${error.message}
            </p>
        `;
    }
}

/**
 * 予測結果をHTMLで整形して表示する関数
 * @param {object} prediction - Geminiから返された予測データ
 */
function displayPredictionResult(prediction) {
    const adviceHtml = prediction.advice.map(adv => `<li>${adv}</li>`).join('');

    predictionResultDiv.innerHTML = `
        <div class="prediction-box">
            <h3 class="prediction-title">感情の天気予報（${prediction.prediction_date}頃の予測）</h3>
            <div class="prediction-scores">
                <p class="score-item happiness-score">ポジティブ: <strong>${prediction.predicted_happiness.toFixed(1)}</strong> / 10.0</p>
                <p class="score-item anger-score">ネガティブ: <strong>${prediction.predicted_anger.toFixed(1)}</strong> / 10.0</p>
            </div>
            
            <p class="prediction-summary">${prediction.tendency_summary}</p>

            <div class="advice-section">
                <h4>日々の意思決定に役立つアドバイス 💡</h4>
                <ul>
                    ${adviceHtml}
                </ul>
            </div>
        </div>
    `;
}

/**
 * 投稿履歴リストをHTMLで表示する関数
 * @param {Array} records 感情レコードの配列
 */
function displayHistoryList(records) {
    historyList.innerHTML = '';
    noHistoryMessage.style.display = records.length === 0 ? 'block' : 'none';

    // 降順に表示（最新の投稿を上にする）
    const reversedRecords = [...records].reverse();

    reversedRecords.forEach(record => {
        const li = document.createElement('li');
        li.className = 'history-item';
        
        // 感情の色分け
        let happinessColor = record.happiness >= 7 ? 'good' : record.happiness >= 4 ? 'neutral' : 'bad';
        let angerColor = record.anger >= 7 ? 'bad' : record.anger >= 4 ? 'neutral' : 'good';

        li.innerHTML = `
            <div class="history-item-meta">
                <span class="history-date">${record.created_at}</span>
                <span class="history-emotion-score happiness ${happinessColor}">ポジティブ: ${record.happiness.toFixed(1)}</span>
                <span class="history-emotion-score anger ${angerColor}">ネガティブ: ${record.anger.toFixed(1)}</span>
            </div>
            <p class="history-text">${record.text_content}</p>
            ${record.image_path ? `
                <div class="history-item-image-container">
                    <img src="${record.image_path}" alt="添付画像" class="history-image">
                </div>
            ` : ''}
        `;
        historyList.appendChild(li);
    });
}

// --- フォーム送信処理 ---
emotionForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    showMessage('info', '感情を分析中です... しばらくお待ちください。');
    setFormSubmitting(true);

    const textContent = document.getElementById('textContent').value.trim();
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    // トグルスイッチの状態を取得 
    const shouldPostToTwitter = postToTwitterToggle.checked;

    if (!textContent && !file) {
        showMessage('error', 'テキストまたは画像を記録してください。');
        resetFormState();
        return;
    }

    const formData = new FormData();
    formData.append('text_content', textContent);
    if (file) {
        formData.append('file', file);
    }

    // フォームデータにトグルスイッチの状態を追加 
    formData.append('post_to_twitter', shouldPostToTwitter);

    try {
        const response = await fetch(API_ANALYZE_URL, {
            method: 'POST',
            body: formData,
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
       
            const twitterMsg = result.twitter_posted ? 'Twitterにも投稿されました。' : 'Twitterへの投稿はスキップされました。';
            showMessage('success', `感情の記録が完了しました！ ポジティブ: ${result.happiness.toFixed(1)}, ネガティブ: ${result.anger.toFixed(1)} ${twitterMsg}`);
            // フォームとファイル入力をリセット
            emotionForm.reset();
            // 文字カウントとプレビューもリセット
            displayImagePreview(null);
            limit();
            // グラフと予測を更新するため、分析タブを再初期化
            const records = await fetchEmotionData();
            drawEmotionChart(records);
            fetchEmotionPrediction(); 

        } else {
            throw new Error(result.error || '分析と記録に失敗しました。');
        }

    } catch (error) {
        console.error("記録エラー:", error);
        showMessage('error', `記録中にエラーが発生しました: ${error.message}`);
    } finally {
        resetFormState();
    }
});


// --- タブ切り替えロジック ---
tabButtons.forEach(button => {
    button.addEventListener('click', async () => {
        const targetId = button.getAttribute('data-target');
        
        // タブのアクティブ状態を切り替える
        tabButtons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        
        // コンテンツの表示を切り替える
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(targetId).classList.add('active');
        
        // 投稿履歴タブがクリックされた場合、データを再取得して表示
        if (targetId === 'post-history') {
            const records = await fetchEmotionData();
            displayHistoryList(records);
        }
        
        // 分析(グラフ)タブがクリックされた場合、グラフ描画と予測を自動実行
        if (targetId === 'analysis-chart') {
             await initApp(); 
        }
    });
});

// 1. ブラウザのデフォルト動作をキャンセルする関数
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
});
// ウィンドウ全体でファイルを開くデフォルト動作を防止
window.addEventListener('drop', preventFileOpen, false);
window.addEventListener('dragover', preventFileOpen, false);

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function preventFileOpen(e) {
    if (e.dataTransfer.items && [...e.dataTransfer.items].some(item => item.kind === 'file')) {
        e.preventDefault();
    }
}

// 2. ドラッグ時の見た目
['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, highlight, false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, unhighlight, false);
});

function highlight(e) {
    dropZone.classList.add('dragover');
}

function unhighlight(e) {
    dropZone.classList.remove('dragover');
}

// 3. ファイルがドロップされた時の処理
dropZone.addEventListener('drop', handleDrop, false);


function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;

    if (files.length) {
        fileInput.files = files;
        
        
        displayImagePreview(files); 
        
        showMessage('success', `${files.length} 件のファイルをドロップしました。`);
    } else {
        showMessage('error', 'ファイルが見つかりませんでした。');
}
}

// fileInputの変更イベントにリスナー
fileInput.addEventListener('change', (e) => {

    displayImagePreview(e.target.files);

    if (e.target.files.length) {
        showMessage('success', `${e.target.files.length} 件のファイルを選択しました。`);
    } else {
        showMessage('message-area', ''); // ファイルがクリアされたらメッセージもクリア
    }
});


// アプリケーション起動時のメイン処理
async function initApp() {
    // 1. 感情データを取得
    const records = await fetchEmotionData();
    
    // データがあればグラフを描画
    if (records && records.length > 0) {
        drawEmotionChart(records);
        
        // **グラフ描画後、自動で感情予測を実行**
        fetchEmotionPrediction();
        
        // メッセージエリアのクリア
        if (messageArea.textContent.includes('まだデータがありません')) {
            messageArea.textContent = '';
            messageArea.className = 'message-area';
        }
        
        // 履歴がない場合のメッセージを非表示
        if (noHistoryMessage) noHistoryMessage.style.display = 'none';

    } else {
        // データがない場合はグラフをクリア
        if (emotionChartInstance) {
            emotionChartInstance.destroy();
            emotionChartInstance = null;
        }
        // 予測エリアにデータ不足メッセージを表示
        predictionResultDiv.innerHTML = '<p class="auth-message">予測に必要な感情データが不足しています。感情を記録してください。</p>';
        showMessage('info', 'まだデータがありません。今日の感情を記録してみましょう！');
        if (noHistoryMessage) noHistoryMessage.style.display = 'block';
    }
}
// --- Twitter連携状態チェック処理 ---
async function checkTwitterAuthStatus() {
    try {
        const response = await fetch('/auth/status'); // ← サーバーでTwitter認証状態を返すエンドポイントを用意
        const result = await response.json();

        const twitterAuthButton = document.getElementById('twitterAuthButton');
        const twitterAuthStatusMessage = document.getElementById('twitterAuthStatusMessage');
        const postToTwitterToggle = document.getElementById('postToTwitterToggle');

        if (result.authenticated) {
            // ✅ 連携済み：ボタンの表示を変更
            twitterAuthButton.textContent = 'Twitter連携済み ✔';
            twitterAuthButton.disabled = true;
            twitterAuthButton.classList.add('connected');
            twitterAuthStatusMessage.textContent = 'Twitterアカウントが連携されています。投稿時に自動ツイートされます。';
            
            // トグルスイッチを有効化
            postToTwitterToggle.disabled = false;
        } else {
            // ❌ 未連携：連携を促す
            twitterAuthButton.textContent = 'Twitterアカウントを連携する';
            twitterAuthButton.disabled = false;
            twitterAuthButton.classList.remove('connected');
            twitterAuthStatusMessage.textContent = 'Twitterアカウントを連携すると、記録と同時に自動投稿されます。';

            // トグルスイッチを無効化＆OFFに
            postToTwitterToggle.checked = false;
            postToTwitterToggle.disabled = true;
        }
    } catch (error) {
        console.error('Twitter認証状態の取得エラー:', error);
    }
}
// Cookieを設定する関数
function setCookie(name, value, days) {
    const date = new Date();
    date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
    const expires = "expires=" + date.toUTCString();
    document.cookie = name + "=" + value + ";" + expires + ";path=/";
}

// Cookieを取得する関数
function getCookie(name) {
    const nameEQ = name + "=";
    const ca = document.cookie.split(';');
    for (let i = 0; i < ca.length; i++) {
        let c = ca[i];
        while (c.charAt(0) === ' ') c = c.substring(1, c.length);
        if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
    }
    return null;
}

// モーダルの表示とスクロール検出
window.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('operationModal');
  const modalBody = document.getElementById('modalBody');
  const closeBtn = document.getElementById('closeModalBtn');
  const overlay = document.getElementById('modalOverlay');

  // Cookieで初回表示かどうかを判定
  const hasSeenModal = getCookie('seenModal');

  // Cookieが無い場合のみモーダルを表示
  if (!hasSeenModal && modal && overlay) {
    modal.style.display = 'block';
    overlay.style.display = 'block';
    modal.style.top = '50%';
    modal.style.left = '50%';
    modal.style.transform = 'translate(-50%, -50%)';
    modalBody.scrollTop = 0;
  }

  // スクロールで閉じるボタンを出す処理
  modalBody.addEventListener('scroll', () => {
    const isBottom = modalBody.scrollTop + modalBody.clientHeight >= modalBody.scrollHeight - 5;
    if (isBottom) {
      closeBtn.style.display = 'block';
    }
  });

  // 閉じるボタンを押したときにCookie保存
  closeBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    overlay.style.display = 'none';

    // モーダルを閉じたことを記録（365日間有効）
    setCookie('seenModal', 'true', 365);
  });

  

 
});


// 「使い方」ボタンがクリックされたら、モーダルを表示
if (howToUseBtn && howToUseModal) {
  howToUseBtn.addEventListener('click', (e) => {
    e.preventDefault(); 

  
    howToUseModal.style.display = 'block'; 
  });
}

// 「✕」ボタンがクリックされたら、モーダルを非表示
if (closeHowToUseModalBtn && howToUseModal) {
  closeHowToUseModalBtn.addEventListener('click', () => {

    
    howToUseModal.style.display = 'none';
  });
}




// アプリ起動時にチェック
checkTwitterAuthStatus();


// アプリケーションを起動
initApp();
