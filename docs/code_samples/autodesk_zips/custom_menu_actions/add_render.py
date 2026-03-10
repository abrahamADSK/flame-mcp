def get_batch_custom_ui_actions():
    def scope_back(selection):
        return len(selection) == 0

    def add_render(selection):
        import flame
        flame.batch.create_node("Render")

    return [
         {
            "name": "PYTHON: BATCH",
            "actions": [
                {
                    "name": "Add Render Node",
                    "isEnabled": scope_back,
                    "execute": add_render
                }
            ]
        }
    ]