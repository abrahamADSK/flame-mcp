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
        if len(current.output_sockets) >= 2 and "OutMatte" in current.output_sockets:
            flame.batch.connect_nodes(current, "OutMatte", mux, "Matte_0")

    def add_mux_to_node_freeze(selection):
        import flame

        current = flame.batch.current_node.get_value()
        time = flame.batch.current_frame
                
        mux = flame.batch.create_node("Mux")
        mux.pos_x = current.pos_x + 200
        mux.pos_y = current.pos_y
        mux.range_active = True
        mux.range_start = time
        mux.range_end = time
        mux.set_context(1, "Result")
        
        flame.batch.connect_nodes(current, "Default", mux, "Default")
        if len(current.output_sockets) >= 2 and "OutMatte" in current.output_sockets:
            flame.batch.connect_nodes(current, "OutMatte", mux, "Matte_0")


    return [
         {
            "name": "PYTHON: NODES",
            "actions": [
                {
                    "name": "Add Mux Node",
                    "isVisible": scope_node,
                    "execute": add_mux_to_node
                },
                {
                    "name": "Add Mux Node and Freeze",
                    "isVisible": scope_node,
                    "execute": add_mux_to_node_freeze
                }
            ]
        }
    ]