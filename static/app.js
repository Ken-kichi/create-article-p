$(function () {
  const socket = io();
  const $start = $("#start");
  const $spinner = $("#spinner");
  const $progressBar = $("#progress-bar");
  const $progressLabel = $("#progress-label");
  const $article = $("#article");
  const $copyButton = $("#copy-article");

  function setLoading(isLoading) {
    if (isLoading) {
      $spinner.removeClass("d-none");
      $start.prop("disabled", true);
    } else {
      $spinner.addClass("d-none");
      $start.prop("disabled", false);
    }
  }

  function updateProgress(rawPercent) {
    const percent = Math.max(0, Math.min(100, rawPercent ?? 0));
    $progressBar
      .css("width", `${percent}%`)
      .attr("aria-valuenow", percent)
      .text(`${percent}%`);
    $progressLabel.text(`${percent}%`);
  }

  function setCopyEnabled(enabled) {
    $copyButton.prop("disabled", !enabled);
  }

  $("#start").click(function () {
    $("#log").empty();
    $article.text("");
    setLoading(true);
    updateProgress(0);
    setCopyEnabled(false);

    socket.emit("start", {
      theme: $("#theme").val()
    });
  });

  socket.on("progress", function (data) {
    $("#log").append(
      `<li class="list-group-item">${data.msg}</li>`
    );
    if (typeof data.percent === "number") {
      updateProgress(data.percent);
    }
  });

  socket.on("done", function (data) {
    $("#log").append(
      `<li class="list-group-item list-group-item-success">完了</li>`
    );
    $article.text(data.article);
    setLoading(false);
    updateProgress(data.percent ?? 100);
    setCopyEnabled(Boolean(data.article));
  });

  socket.on("failed", function (data) {
    $("#log").append(
      `<li class="list-group-item list-group-item-danger">${data.message}</li>`
    );
    setLoading(false);
  });

  $copyButton.click(async function () {
    const text = $article.text().trim();
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
