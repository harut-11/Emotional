const API_HISTORY_URL = '/emotion_history'; // 履歴取得API
const API_ANALYZE_URL = '/analyze_emotion'; // 分析・記録API

const emotionForm = document.getElementById('emotionForm');     
const submitButton = document.getElementById('submitButton');     
const messageArea = document.getElementById('messageArea'); 
const historyList = document.getElementById('historyList'); 
const tabButtons = document.querySelectorAll('.tabButton');   
const noHistoryMessage = document.getElementById('noHistoryMessage'); 

// グローバルなチャートインスタンスを保持するための変数
let emotionChartInstance = null; 

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
    submitButton.textContent = isSubmitting ? '分析中...' : '感情を記録・分析';
}

/**
 * フォームの状態をリセットする関数
 */
function resetFormState() {
    setFormSubmitting(false);
}

/**
 * 感情データをバックエンドAPIから取得する関数
 * @returns {Promise<Array>} 感情レコードの配列
 */
async function fetchEmotionData() {
    try {
        const response = await fetch(API_HISTORY_URL);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json(); 
        return result.data; 
    } catch (error) {
        console.error("感情履歴の取得に失敗しました:", error);
        // ユーザーにメッセージを表示する
        showMessage('error', '過去のデータ読み込みに失敗しました。サーバーが起動しているか確認してください。');
        return [];
    }
}

/**
 * 取得したデータを使用してChart.jsでグラフを描画する関数
 * @param {Array} records - データベースから取得した感情レコードの配列
 */
function drawEmotionChart(records) {
    // 既存のチャートがあれば破棄し、重ねて描画されるのを防ぐ
    if (emotionChartInstance) {
        emotionChartInstance.destroy();
    }
    
    // グラフのラベル（日付）とデータセット（幸福度、怒り）を準備
    const labels = records.map(record => {
        // 日付文字列を整形して表示
        const date = new Date(record.created_at);
        return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    });

    const happinessData = records.map(record => record.happiness);
    const angerData = records.map(record => record.anger);

    const ctx = document.getElementById('emotionChart').getContext('2d');
    emotionChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: '幸福度 (Happiness)',
                    data: happinessData,
                    borderColor: 'rgb(54, 162, 235)', // 青色
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    fill: false,
                    tension: 0.2, // 線のカーブを少し滑らかにする
                },
                {
                    label: '怒りレベル (Anger)',
                    data: angerData,
                    borderColor: 'rgb(255, 99, 132)', // 赤色
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    fill: false,
                    tension: 0.2,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    // Y軸の範囲を固定 (幸福度は-10〜+10、怒りレベルは0〜10)
                    min: -10, 
                    max: 10,
                    title: {
                        display: true,
                        text: '感情スコア'
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                },
                title: {
                    display: true,
                    text: '幸福周期 vs. 怒り周期'
                }
            }
        }
    });
}

// --- フォーム送信処理 ---
emotionForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const textContent = document.getElementById('textContent').value.trim();
    const fileInput = document.getElementById('fileInput');
    const selectedFile = fileInput.files[0];

    // テキストと画像のどちらも空の場合はエラー
    if (!textContent && !selectedFile) {
        showMessage('error', 'テキストまたは写真を添付して感情を記録してください。');
        return;
    }

    setFormSubmitting(true);
    showMessage('info', '感情を分析中です... しばらくお待ちください。');

    try {
        const formData = new FormData();
        
        // テキストコンテンツを追加
        if (textContent) {
           
            formData.append('textContent', textContent);
        }

        // ファイルが選択されていれば追加
        if (selectedFile) {
            formData.append('file', selectedFile);
        }

        const response = await fetch(API_ANALYZE_URL, {
            method: 'POST',
            body: formData, 
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            showMessage('success', `感情を記録しました！幸福度: ${result.emotion_data.happiness}, 怒りレベル: ${result.emotion_data.anger}`);
            
            // 成功したら、グラフを再読み込み
            await initApp();
            
            // フォームをリセット 
            emotionForm.reset();
        } else {
            // API側でエラーが返された場合
            throw new Error(result.error || '分析に失敗しました。');
        }

    } catch (error) {
        console.error("記録エラー:", error);
        showMessage('error', `記録中にエラーが発生しました: ${error.message}`);
    } finally {
        resetFormState();
    }
});

// --- 履歴リスト表示関数 ---
/**
 * 感情レコードの配列からHTMLリストを生成し、表示する
 * @param {Array} records - データベースから取得した感情レコードの配列
 */

function displayHistoryList(records) {
    historyList.innerHTML = ''; // 一旦リストをクリア

    if (!records || records.length === 0) {
        noHistoryMessage.style.display = 'block';
        return;
    }
    
    noHistoryMessage.style.display = 'none';

    // 最新の投稿が上に来るように、配列を逆順にする
    records.slice().reverse().forEach(record => {
        const date = new Date(record.created_at);
        const formattedDate = `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;

        const item = document.createElement('div');
        item.className = 'history-item';
        
        // 感情スコアを強調
        const scoreText = `幸福度: ${record.happiness}, 怒りレベル: ${record.anger}`;
        
        // 画像パスが存在する場合に、<img>タグを生成
        let imageHtml = '';
        if (record.image_path) {
         
            const imageUrl = `/images/${record.image_path}`; 
            imageHtml = `
                <div class="history-item-image-container">
                    <img src="${imageUrl}" alt="記録された画像" class="history-image">
                </div>
            `;
        }

        item.innerHTML = `
            <div class="history-item-meta">
                <span>記録日時: ${formattedDate}</span>
                <strong>${scoreText}</strong>
            </div>
            ${record.text_content ? `<div class="history-item-text">${record.text_content}</div>` : ''}
            ${imageHtml} `;
        
        historyList.appendChild(item);
    });
}


// --- タブ切り替えロジック ---
tabButtons.forEach(button => {
    button.addEventListener('click', async () => {
        const targetId = button.getAttribute('data-target');
        

        tabButtons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        
        // 全てのコンテンツを非表示にし、ターゲットのコンテンツを表示
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(targetId).classList.add('active');
        
        // 投稿履歴タブがクリックされた場合、データを再取得して表示
        if (targetId === 'post-history') {
            const records = await fetchEmotionData();
            displayHistoryList(records);
        }
        
        // 4. 分析(グラフ)タブがクリックされた場合、データが既にあればグラフを再描画
        if (targetId === 'analysis-chart') {
 
             await initApp(); 
        }
    });
});

// アプリケーション起動時のメイン処理
async function initApp() {
    // 1. 感情データを取得
    const records = await fetchEmotionData();
    
    // データがあればグラフを描画
    if (records && records.length > 0) {
        drawEmotionChart(records);
        // データが存在する場合はメッセージをクリア
        if (messageArea.textContent === 'まだデータがありません。今日の感情を記録してみましょう！') {
             messageArea.textContent = '';
             messageArea.className = 'message-area';
        }
    } else {
        // データがない場合の初期メッセージ
        showMessage('info', 'まだデータがありません。今日の感情を記録してみましょう！');
    }
}

// アプリケーションを起動
initApp();
