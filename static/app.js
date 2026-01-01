$(function () {
  const socket = io();
  const $start = $("#start");
  const $spinner = $("#spinner");

  function setLoading(isLoading) {
    if (isLoading) {
      $spinner.removeClass("d-none");
      $start.prop("disabled", true);
    } else {
      $spinner.addClass("d-none");
      $start.prop("disabled", false);
    }
  }

  $("#start").click(function () {
    $("#log").empty();
    $("#article").text("");
    setLoading(true);

    socket.emit("start", {
      theme: $("#theme").val()
    });
  });

  socket.on("progress", function (data) {
    $("#log").append(
      `<li class="list-group-item">${data.msg}</li>`
    );
  });

  socket.on("done", function (data) {
    $("#log").append(
      `<li class="list-group-item list-group-item-success">完了</li>`
    );
    $("#article").text(data.article);
    setLoading(false);
  });

  socket.on("failed", function (data) {
    $("#log").append(
      `<li class="list-group-item list-group-item-danger">${data.message}</li>`
    );
    setLoading(false);
  });
});
