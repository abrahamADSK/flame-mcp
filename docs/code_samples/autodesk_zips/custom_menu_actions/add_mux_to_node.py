def get_batch_custom_ui_actions():
    def scope_node(selection):
        import flame
        for item in selection:
            if isinstance(item, (flame.PyNode)):
                return True
        return False

    def add_mux_to_node(selection):
        import flame
        current = flame.batch.current_node.get_value()
        
        mux = flame.batch.create_node("Mux")
        mux.pos_x = current.pos_x + 200
        mux.pos_y = current.pos_y
        mux.set_context(1, "Result")

        flame.batch.connect_nodes(current, "Default", mux, "Default")

    return [
         {
            "name": "PYTHON: NODES",
            "actions": [
                {
                    "name": "Add Mux Node to Current Node",
                    "isVisible": scope_node,
                    "execute": add_mux_to_node
                }
            ]
        }
    ]