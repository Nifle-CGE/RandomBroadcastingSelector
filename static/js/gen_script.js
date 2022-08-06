function redirectToPost() {
    var post_id = document.getElementById("postIdInput").value;

    if (window.location.href.endsWith("/")) {
        window.location.href += post_id.toString();
    } else {
        window.location.href += "/" + post_id.toString();
    }
}

function invertColorUpvote() {
    upvoteButton = document.getElementById("upvoteButton");
    if (upvoteButton.className.match(/(?:^|\s)w3-text-green(?!\S)/)) {
        upvoteButton.className = upvoteButton.className.replace(/(?:^|\s)w3-text-green(?!\S)/g, "");
    } else {
        upvoteButton.className += " w3-text-green";
    }
}

function invertColorDownvote() {
    downvoteButton = document.getElementById("downvoteButton");
    if (downvoteButton.className.match(/(?:^|\s)w3-text-red(?!\S)/)) { // TODO : vérif que le match fonctionne
        downvoteButton.className = downvoteButton.className.replace(/(?:^|\s)w3-text-red(?!\S)/g, "");
    } else {
        downvoteButton.className += " w3-text-red";
    }
}

function openReportForm() {
    document.getElementById("reportForm").style.display = "block";
}

function closeReportForm() {
    document.getElementById("reportForm").style.display = "none";
}

function enableSubmitButton(submitId, activatorId) {
    button = document.getElementById(submitId);
    button.className = button.className.replace(/(?:^|\s)w3-disabled(?!\S)/g, "");
    button.disabled = false;

    document.getElementById(activatorId).style.display = "none";
}