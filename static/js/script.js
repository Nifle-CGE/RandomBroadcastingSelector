function redirectToPost() {
    let post_id = document.getElementById("postIdInput").value;

    if (window.location.href.endsWith("/")) {
        window.location.href += post_id.toString();
    } else {
        window.location.href += "/" + post_id.toString();
    }
}

async function liveVote(action) {
    const data = new URLSearchParams();
    data.append("action", action);
    let resp = await fetch("/vote/", {
        method: "POST",
        body: data
    });
    let text = await resp.text()

    if (text !== action) {
        alert(text);
    }

    let downvoteButton = document.getElementById("downvoteButton");
    let downvoteNum = document.getElementById("downvote_num");
    let upvoteButton = document.getElementById("upvoteButton");
    let upvoteNum = document.getElementById("upvote_num");

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
    let button = document.getElementById(submitId);
    button.style.cursor = "default";
    button.disabled = false;

    document.getElementById(activatorId).className += " w3-hide";
}

function changeReportFormBottomInputLabel(target_label) {
    ["", "_harassement", "_mild_language", "_link", "_offensive_name"].forEach(element => {
        document.getElementById("quote_label" + element).hidden = true;
    });

    document.getElementById("quote_label_" + target_label.value).hidden = false;

    document.getElementById("quote_input").required = (target_label.value !== "offensive_name");
}

function showDropdown(dropdownId) {
    let dropdown = document.getElementById(dropdownId);

    if (dropdown.className.indexOf("w3-show") == -1) {
        dropdown.className += " w3-show";
    } else {
        dropdown.className = dropdown.className.replace(" w3-show", "");
    }
}

function updateCharCounter(inputId, counterId, colorbase = "black", colormax = "black") {
    let counter = document.getElementById(counterId)
    let max = Number(counter.innerHTML.split("/")[1])
    let current = document.getElementById(inputId).value.length
    counter.innerHTML = current + "/" + max
    if (current < max) {
        counter.style.color = colorbase
    } else if (max === current) {
        counter.style.color = colormax
    } else {
        counter.style.color = "red"
    }
}

function countDown(counterId) {
    let nums = document.getElementById(counterId).innerText.match(/(\d+)/g).map(x => parseInt(x))
    if (nums.reduce((a, b) => a + b, 0) === 0) { // if timer is over refresh
        return location.reload()
    }
    let newnums = [0, 0, 0, 0]

    // seconds
    let carry = 0
    newnums[3] = nums[nums.length - 1] - 1
    if (newnums[3] === -1) {
        newnums[3] = 59
        carry = 1
    }

    // minutes
    if (nums.length > 1) {
        newnums[2] = nums[nums.length - 2] - carry
        if (newnums[2] === -1) {
            newnums[2] = 59
            carry = 1
        } else {
            carry = 0
        }

        // hours
        if (nums.length > 2) {
            newnums[1] = nums[nums.length - 3] - carry
            if (newnums[1] === -1) {
                newnums[1] = 23
                carry = 1
            } else {
                carry = 0
            }

            // days
            if (nums.length > 3) {
                newnums[0] = nums[nums.length - 4] - carry
            }
        }
    }

    // export newnums to the string
    let splitted = document.getElementById(counterId).innerText.split(/\d+/)
    for (let index = 1; index < splitted.length; index++) {
        splitted[splitted.length - index] = newnums[newnums.length - index].toString() + " " + splitted[splitted.length - index]
    }

    document.getElementById(counterId).innerText = splitted.join(" ")
}

function countUp(counterId) {
    let nums = document.getElementById(counterId).innerText.match(/(\d+)/g).map(x => parseInt(x))
    let newnums = [0, 0, 0, 0]

    // seconds
    let carry = 0
    newnums[3] = nums[nums.length - 1] + 1
    if (newnums[3] === 60) {
        newnums[3] = 0
        carry = 1
    } else {
        carry = 0
    }

    // minutes
    if (nums.length > 1) {
        newnums[2] = nums[nums.length - 2] + carry
        if (newnums[2] === 60) {
            newnums[2] = 0
            carry = 1
        } else {
            carry = 0
        }

        // hours
        if (nums.length > 2) {
            newnums[1] = nums[nums.length - 3] + carry
            if (newnums[1] === 24) {
                newnums[1] = 0
                carry = 1
            } else {
                carry = 0
            }

            // days
            if (nums.length > 3) {
                newnums[0] = nums[nums.length - 4] + carry
            }
        }
    }

    // export newnums to the string
    let splitted = document.getElementById(counterId).innerText.split(/\d+/)
    for (let index = 1; index < splitted.length; index++) {
        splitted[splitted.length - index] = newnums[newnums.length - index].toString() + " " + splitted[splitted.length - index]
    }

    document.getElementById(counterId).innerText = splitted.join(" ")
}

function toggleModal(modalId) {
    let modal = document.getElementById(modalId)
    if (modal.style.display === 'none') {
        modal.style.display = 'block'
    } else {
        modal.style.display = 'none'
    }
}