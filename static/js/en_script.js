function changeReportFormBottomInputLabel(target_label) {
    var label = ""
    switch (target_label) {
        case "harassement":
            label = "You have to quote the part of the message that is concerned.";
            break;

        case "mild-lang":
            label = "You have to quote the part of the message that isn't family friendly.";
            break;

        case "link":
            label = "You have to quote the link.";
            break;
    }
    document.getElementById("quote_label").innerHTML = label;
}

function validateReportForm(message) {
    var quote = document.getElementById("quote_input").value;
    if (!message.includes(quote)) {
        alert("The quote you supplied isn't in the broadcast.");
        return false;
    }

    var rx = new RegExp("[\w']+", "g");
    var splitted_quote = new Array();
    while ((match = rx.exec(quote)) !== null) {
        splitted_quote.push(match);
    }
    splitted_quote = splitted_quote.filter(Boolean); // to remove empty elements
    if (splitted_quote.length < 2) {
        alert("The quote you supplied has only got one word when it has to have at least two.");
        return false;
    }

    var splitted_msg = new Array();
    while ((match = rx.exec(message)) !== null) {
        splitted_msg.push(match);
    }
    splitted_msg = splitted_msg.filter(Boolean); // to remove empty elements

    var quote_index = 0;
    var is_checking = false;
    for (let index = 0; index < splitted_msg.length; index++) {
        if (splitted_quote[quote_index] === splitted_msg[index]) {
            quote_index += 1;
            is_checking = quote_index !== splitted_quote.length;
        } else if (is_checking) {
            alert("Your quote isn't valid because you either cut a word in half or put words in a different order than it was in the original message.");
            return false;
        }
    }

    return true;
}