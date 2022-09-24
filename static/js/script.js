function redirectToPost() {
    var post_id = document.getElementById("postIdInput").value;

    if (window.location.href.endsWith("/")) {
        window.location.href += post_id.toString();
    } else {
        window.location.href += "/" + post_id.toString();
    }
}

async function liveVote(action) {
    const data = new URLSearchParams();
    data.append("action", action);
    var resp = await fetch("/vote/", {
        method: "POST",
        body: data
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
        if (upvoteButton.className.indexOf(" w3-text-green w3-hover-text-green") !== -1) {
            upvoteButton.className = upvoteButton.className.replace(" w3-text-green w3-hover-text-green", "");
            upvoteNum.innerHTML = parseInt(upvoteNum.innerHTML) - 1
        } else {
            upvoteButton.className += " w3-text-green w3-hover-text-green";
            upvoteNum.innerHTML = parseInt(upvoteNum.innerHTML) + 1

            if (downvoteButton.className.indexOf(" w3-text-red w3-hover-text-red") !== -1) {
                downvoteButton.className = downvoteButton.className.replace(" w3-text-red w3-hover-text-red", "");
                downvoteNum.innerHTML = parseInt(downvoteNum.innerHTML) - 1
            }
        }
    } else if (action === "downvote") {
        if (downvoteButton.className.indexOf(" w3-text-red w3-hover-text-red") !== -1) {
            downvoteButton.className = downvoteButton.className.replace(" w3-text-red w3-hover-text-red", "");
            downvoteNum.innerHTML = parseInt(downvoteNum.innerHTML) - 1
        } else {
            downvoteButton.className += " w3-text-red w3-hover-text-red";
            downvoteNum.innerHTML = parseInt(downvoteNum.innerHTML) + 1

            if (upvoteButton.className.indexOf(" w3-text-green w3-hover-text-green") !== -1) {
                upvoteButton.className = upvoteButton.className.replace(" w3-text-green w3-hover-text-green", "");
                upvoteNum.innerHTML = parseInt(upvoteNum.innerHTML) - 1
            }
        }
    }
}

function enableSubmitButton(submitId, activatorId) {
    button = document.getElementById(submitId);
    button.style.cursor = "default";
    button.disabled = false;

    document.getElementById(activatorId).hidden = true;
}

function changeReportFormBottomInputLabel(target_label) {
    document.getElementById("quote_label").hidden = true;
    document.getElementById("quote_label_harassement").hidden = true;
    document.getElementById("quote_label_mild_language").hidden = true;
    document.getElementById("quote_label_link").hidden = true;
    document.getElementById("quote_label_offensive_name").hidden = true;

    document.getElementById("quote_label_" + target_label.value).hidden = false;

    document.getElementById("quote_input").required = (target_label.value !== "offensive_name");
}

function showDropdown(dropdownId) {
    dropdown = document.getElementById(dropdownId);

    if (dropdown.className.indexOf("w3-show") == -1) {
        dropdown.className += " w3-show";
    } else {
        dropdown.className = dropdown.className.replace(" w3-show", "");
    }
}

function updateCharCounter(inputId, counterId, colorbase = "black", colormax = "black") {
    counter = document.getElementById(counterId)
    max = Number(counter.innerHTML.split("/")[1])
    current = document.getElementById(inputId).value.length
    counter.innerHTML = current + "/" + max
    if (current < max) {
        counter.style.color = colorbase
    } else if (max === current) {
        counter.style.color = colormax
    } else {
        counter.style.color = "red"
    }
}