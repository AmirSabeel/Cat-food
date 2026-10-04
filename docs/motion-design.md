# Pet motion update

The homepage uses the two client-supplied pet images and an original two-pose tabby sprite for the scroll scene. A PLAISIR BIO 100g product from the supplied catalogue is featured; no sales ranking or trending claim is made.

- `static/images/pets-portrait.jpeg`: client upload IMG_0727.jpeg, displayed with CSS framing.
- `static/images/pets-peeking.jpeg`: client upload IMG_0728.jpeg, displayed with CSS framing and a scroll reveal.
- `static/images/cat-gaze-sprite.png`: generated with the built-in imagegen tool using the right-hand tabby in IMG_0727.jpeg as reference. Transparent two-cell sprite, forward-facing and looking up.
- `static/images/featured-cat-food.jpg`: original product image extracted from the client catalogue.

Generation prompt: Create a photorealistic transparent two-cell, side-by-side animation sprite of the same brown tabby from the supplied reference. Lock markings, lighting, body scale and paws. Left: looking toward the viewer. Right: chin lifted, head slightly tilted back and eyes looking clearly upward. Align both poses on the same invisible ledge; include ears, whiskers and paws. No dogs, background, ledge or text. Wide 2:1 canvas.

The two poses crossfade with scroll progress while the actual product pack translates, rotates and scales. Animation uses passive scroll listeners and requestAnimationFrame, with Pause motion, Skip section and prefers-reduced-motion support. No scroll locking or wheel interception is used.

References inspected for motion direction: Pinterest pins 955748352150807089 (pet-food website) and 64880050872598519 (floating mango-product presentation). Reference videos are not embedded or copied into the website.

Validated in a local browser at 1440×1000 and 390×844: forward-to-upward gaze transition, product details, pause, skip, reduced motion, image loading, no horizontal overflow and no JavaScript errors. Existing product, cart and checkout code is preserved. The hosted private preview still does not submit orders or accept payments.
