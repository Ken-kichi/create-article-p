$("#run").click(function() {
    const theme = $("#theme").val();
    if (theme){
        alert("Selected theme: " + theme);
        return;
    }

    $("#result").text("Generating...");
    $.ajax({
        url: "/generate",
        method: "POST",
        contentType: "application/json",
        data: JSON.stringify({ theme }),
        success: function(res){
            $("#result").text(res.article);
        },
        error:function(err){
            $("#result").text("Error: " + err.responseText);
        }
    })
});
