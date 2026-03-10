def get_timeline_custom_ui_actions():
    def scope_markers(selection):
        import flame
        for item in selection:
            if isinstance(item, (flame.PyMarker)):
                if isinstance(item.parent, (flame.PySegment)):
                    return True
            return False

    def markers_length(selection):
        import flame
        for item in selection:
            parent = item.parent
            item.location = parent.record_in
            item.duration = parent.record_duration

    return [
         {
            "name": "PYTHON: MARKERS",
            "actions": [
                {
                    "name": "Set Segment Markers to Segment Duration",
                    "isVisible": scope_markers,
                    "execute": markers_length
                }
            ]
        }
    ]

