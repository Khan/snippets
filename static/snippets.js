$(function() {

    // save save the state of the snippet in .data and disable buttons
    var saveLocalSnippet = function(textarea) {
        var $parentForm = $(textarea).closest("form");
        $(textarea).data("orig", $(textarea).val());
        $parentForm.removeClass("dirty").
            find(".undo-button, .save-button").
            prop("disabled", true);
        $parentForm.find(".snippet-preview-container").hide();
    };

    var handleChange = function handleChange() {
        var $parentForm = $(".user-snippet-form");
        var $previewText = $parentForm.find(".snippet-preview");
        var $textarea = $(".snippet textarea");

        var dirty = $textarea.val() !== $textarea.data("orig");
        $parentForm.toggleClass("dirty", dirty);

        $parentForm.find(".undo-button, .save-button").
            prop("disabled", !dirty);

        var $preview = $parentForm.find(".snippet-preview-container");
        if (dirty) {
            var textVal = $textarea.val();
            $(".snippet-tag-none")[!textVal ? "show" : "hide"]();

            if ($parentForm.find("input[name='is_markdown']")[0].checked) {
                textVal = window.marked(textVal);
            }

            $previewText.html(textVal);
            $preview.show();
        } else {
            $preview.hide();
        }
    };

    window.marked.setOptions({sanitize: true});
    $(".snippet-text-markdown").each(function(i, v) {
        v.innerHTML = window.marked(v.innerHTML);
    });

    // save the state of each textarea to allow undos
    $(".snippet textarea").each(function(i, v) {
        saveLocalSnippet(v);
    });

    $("input[name=private]").on("change", function(e) {
        $(".snippet-tag-private")[this.checked ? "show" : "hide"]();
        handleChange.call(this);
    });

    $("input[name=is_markdown]").on("change", function() {
        var isMarkdown = this.checked;
        var $previewText = $(".snippet-preview");

        $previewText.toggleClass("snippet-text-markdown", isMarkdown);
        $previewText.toggleClass("snippet-text", !isMarkdown);

        handleChange.call(this);
    });

    // measure dirtiness on change
    $(".snippet textarea").on("keyup change", handleChange);

    // catch form submissions, submit and disable buttons
    $(".snippet form").on("submit", function(e) {
        e.preventDefault();
        var vals = $(this).serialize();
        var $textarea = $(this).find("textarea");
        var disableUndoOnUpdate = function(d, ts, jqx) {
            saveLocalSnippet($textarea);
        };
        $.post($(this).attr("action"), vals, disableUndoOnUpdate);
    });

    // undo button behavior
    $(".snippet .undo-button").on("click", function(e) {
        e.preventDefault();
        var $parentForm = $(this).closest("form");
        var $textarea = $parentForm.find("textarea");
        $textarea.val($textarea.data("orig"));
        $parentForm.removeClass("dirty").
            find(".undo-button, .save-button").
            prop("disabled", true);
        $parentForm.find(".snippet-preview-container").hide();
    });

    // confirm window closings :)
    $(window).on("beforeunload", function() {
        var dirtySnippets = $(".dirty").length;
        if (dirtySnippets) {
            var s = dirtySnippets > 1 ? "s." : ".";
            var msg = "Hey!!! You have " + dirtySnippets +
                " unsaved snippet" + s;
            return msg;
        }
    });
});
