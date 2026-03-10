def get_timeline_custom_ui_actions():
    def scope_segment(selection):
        import flame
        for item in selection:
            if isinstance(item, (flame.PySegment)):
                return True
            return False

    def create_marker(selection):
        import flame
        for item in selection:
            parent = item.parent
            while ((isinstance(parent, (flame.PyClip)) != True) and parent):
                parent = parent.parent
            duration = item.record_duration
            marker = parent.create_marker(item.record_in)
            marker.duration = duration

    def create_seg_marker(selection):
        import flame
        for item in selection:
            duration = item.record_duration
            marker = item.create_marker(item.record_in)
            marker.duration = duration

    return [
         {
            "name": "PYTHON: SEGMENT",
            "actions": [
                {
                    "name": "Create Marker Based on Segment Duration",
                    "isVisible": scope_segment,
                    "execute": create_marker
                },
                {
                    "name": "Create Segment Marker Based on Segment Duration",
                    "isVisible": scope_segment,
                    "execute": create_seg_marker
                },
            ]
        }
    ]
