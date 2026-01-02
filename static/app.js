$(function () {
  /** Socket.IOとDOM要素を初期化し、記事生成UIを制御する即時関数。 */
  const socket = io();
  const $start = $("#start");
  const $spinner = $("#spinner");
  const $progressBar = $("#progress-bar");
  const $progressLabel = $("#progress-label");
  const $article = $("#article");
  const $copyButton = $("#copy-article");

  /**
   * ローディング状態を切り替え、ボタンとスピナーの表示を更新する。
   * @param {boolean} isLoading - trueなら処理中としてUIをロックする
   */
  function setLoading(isLoading) {
    if (isLoading) {
      $spinner.removeClass("d-none");
      $start.prop("disabled", true);
    } else {
      $spinner.addClass("d-none");
      $start.prop("disabled", false);
    }
  }

  /**
   * 進捗率を0〜100の範囲に正規化し、プログレスバーへ反映する。
   * @param {number} rawPercent - サーバーから渡される生の進捗値
   */
  function updateProgress(rawPercent) {
    const percent = Math.max(0, Math.min(100, rawPercent ?? 0));
    $progressBar
      .css("width", `${percent}%`)
      .attr("aria-valuenow", percent)
      .text(`${percent}%`);
    $progressLabel.text(`${percent}%`);
  }

  /**
   * 完成記事コピー用ボタンの有効/無効を切り替える。
   * @param {boolean} enabled - trueでボタンを押下可能にする
   */
  function setCopyEnabled(enabled) {
    $copyButton.prop("disabled", !enabled);
  }

  /** テーマ入力から記事生成を開始するクリックハンドラ。 */
  $("#start").click(function () {
    $("#log").empty();
    $article.val("");
    setLoading(true);
    updateProgress(0);
    setCopyEnabled(false);

    socket.emit("start", {
      theme: $("#theme").val()
    });
  });

  /** LangGraph進捗イベントを受信し、ログと進捗バーを更新する。 */
  socket.on("progress", function (data) {
    $("#log").append(
      `<li class="list-group-item">${data.msg}</li>`
    );
    if (typeof data.percent === "number") {
      updateProgress(data.percent);
    }
  });

  /** 記事完成イベントを受信し、本文出力とUIリセットを行う。 */
  socket.on("done", function (data) {
    $("#log").append(
      `<li class="list-group-item list-group-item-success">完了</li>`
    );
    $article.val(data.article ?? "");
    setLoading(false);
    updateProgress(data.percent ?? 100);
    setCopyEnabled(Boolean(data.article));
  });

  /** エラー通知を受信した際、ログに表示しローディング状態を解除する。 */
  socket.on("failed", function (data) {
    $("#log").append(
      `<li class="list-group-item list-group-item-danger">${data.message}</li>`
    );
    setLoading(false);
  });

  /** 完成した記事をクリップボードへコピーするクリックハンドラ。 */
  $copyButton.click(async function () {
    const text = ($article.val() || "").trim();
    if (!text) {
      return;
    }
    const original = $copyButton.text();
    try {
      await navigator.clipboard.writeText(text);
      $copyButton.text("コピーしました");
      setTimeout(() => $copyButton.text(original), 2000);
    } catch (err) {
      console.error("Clipboard copy failed", err);
      $copyButton.text("コピー失敗");
      setTimeout(() => $copyButton.text(original), 2000);
    }
  });
});
