function redirectToPost() {
    var post_id = document.getElementById("postIdInput").value;

    if (window.location.href.endsWith("/")) {
        window.location.href += post_id.toString();
    } else {
        window.location.href += "/" + post_id.toString();
    }
}

async function invertColorVote(action) {
    var resp = await fetch("/" + action + "-callback", {
        method: "POST"
    });
    var text = await resp.text()

    if (text !== action) {
        alert(text);
    }

    downvoteButton = document.getElementById("downvoteButton");
    downvoteNum = document.getElementById("downvote_num");
    upvoteButton = document.getElementById("upvoteButton");
    upvoteNum = document.getElementById("upvote_num");

    if (action === "upvote") {
        if (upvoteButton.className.match(/(?:^|\s)w3-text-green w3-hover-text-green(?!\S)/)) {
            upvoteButton.className = upvoteButton.className.replace(/(?:^|\s)w3-text-green w3-hover-text-green(?!\S)/g, "");
            upvoteNum.innerHTML = parseInt(upvoteNum.innerHTML) - 1
        } else {
            upvoteButton.className += " w3-text-green w3-hover-text-green";
            upvoteNum.innerHTML = parseInt(upvoteNum.innerHTML) + 1

            if (downvoteButton.className.match(/(?:^|\s)w3-text-red w3-hover-text-red(?!\S)/)) {
                downvoteButton.className = downvoteButton.className.replace(/(?:^|\s)w3-text-red w3-hover-text-red(?!\S)/g, "");
                downvoteNum.innerHTML = parseInt(downvoteNum.innerHTML) - 1
            }
        }
    } else {
        if (downvoteButton.className.match(/(?:^|\s)w3-text-red w3-hover-text-red(?!\S)/)) {
            downvoteButton.className = downvoteButton.className.replace(/(?:^|\s)w3-text-red w3-hover-text-red(?!\S)/g, "");
            downvoteNum.innerHTML = parseInt(downvoteNum.innerHTML) - 1
        } else {
            downvoteButton.className += " w3-text-red w3-hover-text-red";
            downvoteNum.innerHTML = parseInt(downvoteNum.innerHTML) + 1

            if (upvoteButton.className.match(/(?:^|\s)w3-text-green w3-hover-text-green(?!\S)/)) {
                upvoteButton.className = upvoteButton.className.replace(/(?:^|\s)w3-text-green w3-hover-text-green(?!\S)/g, "");
                upvoteNum.innerHTML = parseInt(upvoteNum.innerHTML) - 1
            }
        }
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