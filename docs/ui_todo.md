# Face-and-Names v2 – UI TODOs Before Coding

Checklist to convert wireframes into actionable PyQt scaffolding.

- Choose Qt version (PyQt6 preferred); verify module needs (widgets, charts vs. custom histograms, no webengine unless required).
- Define main window class structure: header, nav, content stack, footer components.
- Define shared face tile widget: states (selected/inactive), labels, hover actions, right-click preview hook. Skeleton added in `ui/components/face_tile.py`; wire into Faces/Naming/Prediction flows.
- Plan virtualization approach for grids: Qt item views vs. custom widget pool; target performance on large datasets. Interim paging (`Load more`, default page size 200) is in place for folder thumbnails.
- Map keyboard shortcuts and focus order for primary actions (accept/rename/delete/select all/navigate clusters).
- Decide charting approach for histograms (confidence, cluster sizes): lightweight custom paint vs. library.
- Design data models for filters (scope, confidence, unnamed-only, differs-from-name, date range, groups) with PyQt bindings.
- Sketch dialogs: rename, bulk assign person ID, merge people, choose clusters, conflict prompts for import/export.
- Plan overlay editor for bboxes: image viewer widget with draw/edit tools; saving bboxes and assignments.
- Define progress UI components shared by ingest/clustering/prediction jobs with cancel/skip/retry hooks.
- Set accessibility targets: labels, tab order, focus visuals, tooltip content style guide.
- Theme/density options: light/dark/system; compact vs. comfortable spacing.
