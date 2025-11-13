# face-and-names
my test project for AI driven codes that is slightly more complex. No classic coding - english is the coding language (actually it is python)

# todo
- add code to check if the yolov11n-face.pt is loaded. if not load it at startup
- filter on face analysis on the images of the circles on top (month of image)
- add a filter to find images (person 1 and person 2 and not person 3)
- improve startup time drastically, only make important stuff

## Face Import Folder Structure

When you import photos, the application records each image using a `(base_folder, sub_folder, filename)` triple:

- `base_folder` – the absolute path of the directory you selected in the UI (or, if the image is in a deeper tree, the parent of the folder that directly contains the file)
- `sub_folder` – the leaf folder that contains the image; it is stored as an empty string when the file lives directly inside the base folder
- `filename` – the file name (e.g., `IMG_0001.JPG`)

This allows imports from both `…/Photos/<album>/<image>.jpg` hierarchies and flat folders without crashing `_get_image_location`.

## Model Artifacts

Trained recognition assets live in `face_recognition_models/` and are now saved as `state_dict`s:

- `mtcnn_complete.pth` – weights for the detector backbone (`facenet_pytorch.MTCNN`)
- `face_encoder_complete.pth` – weights for `facenet_pytorch.InceptionResnetV1`
- `face_classifier.joblib` / `label_encoder.joblib` – scikit-learn artifacts built from the embeddings

During inference, every face crop passes through the shared preprocessing utility (`src/utils/face_preprocessing.py`) so that detection, training, and prediction all normalize images identically.
