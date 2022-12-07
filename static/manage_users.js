// Handlers for the manage_users.html template.
//
$(function() {
    // Function to attach to each 'hide' button that toggles the hide state.
    function toggleHide(event) {
        var $inputButton = event.target;
        var email = $($inputButton).attr("data-email");
        if ($inputButton.value === "Hide") {
            $inputButton.value = "Hiding...";
            $inputButton.disabled = true;
            $.post("/admin/manage_users", {action: "hide", email: email})
                .then(function() {
                    $inputButton.name = "unhide " + email;
                    $inputButton.value = "Unhide";
                    $inputButton.disabled = false;
                }, function() {
                    $inputButton.value = "Re-hide (hiding failed!)";
                    $inputButton.disabled = false;
                });
        } else {
            $inputButton.value = "Unhiding...";
            $inputButton.disabled = true;
            $.post("/admin/manage_users", {action: "unhide", email: email})
                .then(function() {
                    $inputButton.name = "hide " + email;
                    $inputButton.value = "Hide";
                    $inputButton.disabled = false;
                }, function() {
                    $inputButton.value = "Re-unhide (unhiding failed!)";
                    $inputButton.disabled = false;
                });
        }
    }

    function doDelete(event) {
        var $inputButton = event.target;
        var email = $($inputButton).attr("data-email");
        $inputButton.value = "Deleting...";
        $inputButton.disabled = true;
        $.post("/admin/manage_users", {action: "delete", email: email})
            .then(function() {
                $inputButton.value = "Deleted";
                // TODO(csilvers): change the whole row to indicate deleted
            }, function() {
                $inputButton.value = "Re-delete (deleting failed!)";
                $inputButton.disabled = false;
            });
    }

    $(".hide-account-button").map(function() {
        $(this).on("click", toggleHide.bind(this));
    });

    $(".delete-account-button").map(function() {
        $(this).on("click", doDelete.bind(this));
    });
});
