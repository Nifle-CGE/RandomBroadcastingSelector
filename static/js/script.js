function redirectToPost() {
    var post_id = document.getElementById("post_id_input").value;

    if (window.location.href.endsWith("/")) {
        window.location.href += post_id.toString();
    } else {
        window.location.href += "/" + post_id.toString();
    }
}

function invertColorUpvote() {
    if (document.getElementById("upvote_button").className.match(/(?:^|\s)w3-text-green(?!\S)/)) {
        document.getElementById("upvote_button").className = document.getElementById("upvote_button").className.replace(/(?:^|\s)w3-text-green(?!\S)/g, "")
    } else {
        document.getElementById("upvote_button").className += " w3-text-green"
    }
}

function invertColorDownvote() {
    if (document.getElementById("downvote_button").className.match(/(?:^|\s)w3-text-red(?!\S)/)) {
        document.getElementById("downvote_button").className = document.getElementById("downvote_button").className.replace(/(?:^|\s)w3-text-red(?!\S)/g, "")
    } else {
        document.getElementById("downvote_button").className += " w3-text-red"
    }
}