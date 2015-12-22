// Handlers for the user_snippets.html template.
//
$(function() {
    // A User Snippet class constructor to be called on each
    // `.user-snippet-form`. Handles a bunch of side-effects and adds event
    // listeners to form children within the constructor.
    function Snippet($parentForm) {
        this.$el = $parentForm;

        // Child elements of the parent form.
        // We use "secret" instead of "private" because "private" is reserved.
        this.$markdownInput = $parentForm.find("input[name=is_markdown]");
        this.$noneTag = $parentForm.find(".snippet-tag-none");
        this.$preview = $parentForm.find(".snippet-preview-container");
        this.$previewText = $parentForm.find(".snippet-preview");
        this.$saveButton = $parentForm.find(".save-button");
        this.$secretInput = $parentForm.find("input[name=private]");
        this.$secretTag = $parentForm.find(".snippet-tag-private");
        this.$textarea = $parentForm.find("textarea");
        this.$undoButton = $parentForm.find(".undo-button");

        // Child element collections.
        this.$buttons = this.$saveButton.add(this.$undoButton);
        this.$inputs =
            this.$markdownInput.add(this.$secretInput).add(this.$textarea);

        // Internal state of the Snippet.
        // Matches the initial Snippet values to allow undo and dirty checks.
        this.oldState = {};
        // Holds the current Snippet values. We'll initialize it soon...
        this.state = {
            content: null,
            markdown: null,
            secret: null,
        };

        // Attach event listeners.
        // Internal state should be kept up-to-date with our inputs.
        this.$textarea.on("keyup change", (function() {
            this.state.content = this.$textarea.val();
        }).bind(this));
        this.$markdownInput.on("change", (function() {
            this.state.markdown = this.$markdownInput.prop("checked");
        }).bind(this));
        this.$secretInput.on("change", (function() {
            this.state.secret = this.$secretInput.prop("checked");
        }).bind(this));

        // Pull our initial input values into internal state.
        this.$inputs.trigger("change");

        // Re-render whenever an input changes.
        this.$inputs.on("keyup change", this.render.bind(this));

        // Save and undo buttons, available when state is dirty.
        this.$undoButton.on("click", this.undo.bind(this));
        this.$saveButton.on("click", this.submit.bind(this));

        // Finally, save (this also triggers a render).
        this.save();
    }

    // Save the internal state of a Snippet to allow undos.
    Snippet.prototype.save = function(e) {
        e && e.preventDefault && e.preventDefault();
        // Save the current values into .data.
        this.oldState.content = this.state.content;
        this.oldState.markdown = this.state.markdown;
        this.oldState.secret = this.state.secret;

        // Disable the buttons.
        this.render();
    };

    // Recover the original values from `this.oldState`.
    Snippet.prototype.undo = function(e) {
        e && e.preventDefault && e.preventDefault();
        this.$textarea.val(this.oldState.content);
        this.$markdownInput.prop("checked", this.oldState.markdown);
        this.$secretInput.prop("checked", this.oldState.secret);

        // HACK: Reset internal state and disable the buttons.
        this.$inputs.trigger("change");
    };

    // Check if a snippet is "dirty", meaning its initial state no-longer
    // matches the values of all its inputs.
    Snippet.prototype.checkIfDirty = function() {
        return (
            this.state.content !== this.oldState.content ||
            this.state.markdown !== this.oldState.markdown ||
            this.state.secret !== this.oldState.secret
        );
    };

    // Run some side-effects on the Snippet's elements. This could be diffed,
    // but it seems to run well enough as-is.
    Snippet.prototype.render = function() {
        var isDirty = this.checkIfDirty();

        this.$el.toggleClass("dirty", isDirty);
        this.$buttons.prop("disabled", !isDirty);
        this.$noneTag.toggle(!this.state.content);
        this.$previewText.html(this.state.markdown ?
            window.marked(this.state.content) : this.state.content);
        this.$secretTag[this.state.secret ? "show" : "hide"]();
        this.$previewText.toggleClass("snippet-text-markdown",
            this.state.markdown);
        this.$previewText.toggleClass("snippet-text", !this.state.markdown);
    };

    // Catch form submissions, submit and disable buttons.
    Snippet.prototype.submit = function(e) {
        e && e.preventDefault && e.preventDefault();
        $.post(this.$el.attr("action"), this.$el.serialize(),
            this.save.bind(this));
    };

    // Create a Snippet for each week shown.
    var snippets = $(".user-snippet-form").map(function() {
        return new Snippet($(this));
    }).get();

    // Confirm window closings :)
    $(window).on("beforeunload", function() {
        var numDirty = snippets.filter(function(snippet) {
            return snippet.checkIfDirty();
        }).length;

        if (numDirty) {
            var s = numDirty > 1 ? "s." : ".";
            var msg = "Hey!!! You have " + numDirty + " unsaved snippet" + s;
            return msg;
        }
    });
});
