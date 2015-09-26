$(function() {

    // save save the state of the snippet in .data and disable buttons
    var saveLocalSnippet = function(textarea) {
        var $parentForm = $(textarea).closest("form");
        $(textarea).data("orig", $(textarea).val());
        $parentForm.removeClass("dirty").
            find(".undo-button, .save-button").
            prop("disabled", true);
        $parentForm.find(".snippet-markdown-preview").hide();
    };

    // save the state of each textarea to allow undos
    $(".snippet textarea").each(function(i, v) {
        saveLocalSnippet(v);
    });

    // measure dirtiness on keyup
    $(".snippet textarea").on("keyup blur", function() {
        var $parentForm = $(this).closest("form");

        var dirty = $(this).val() !== $(this).data("orig");
        $parentForm.toggleClass("dirty", dirty);

        $parentForm.find(".undo-button, .save-button").
            prop("disabled", !dirty);

        var $preview = $parentForm.find(".snippet-markdown-preview");
        var $previewText = $parentForm.find(".snippet-text-markdown");
        if (dirty &&
              $parentForm.find("input[name='is_markdown']").prop('checked')) {
            $previewText.html(marked($(this).val()));
            $preview.show();
        } else {
            $preview.hide();
        }
    });

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
