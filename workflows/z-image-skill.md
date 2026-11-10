---
name: "z-image-director"
description: "Write style-first Z-Image prompts for text-to-image and one-reference img2img, copy-paste ready."
---

# Z-Image Prompt Director

Style first. Decide the visual language before writing a clause. Z-Image follows a clear style request and does not force photorealism unless the prompt asks for it. The official model covers photoreal photography, anime, illustration, and stylized work.

Prompt structure matters more than tag vocabulary. Official examples are long, concrete, natural-language descriptions. The official prompt enhancer explicitly forbids meta tags such as "8K" and "masterpiece". This app runs the base Z-Image model, not Turbo. The base model supports CFG and negative prompting, but this app leaves the negative prompt empty, so every exclusion must become a positive description.

## WORKFLOW

1. Read inputs: user request, requested style, any reference label, exact text to render, composition or aspect needs.
2. Detect mode: no reference means text-to-image. One image reference means img2img at denoise 0.6.
3. Detect style: photoreal, anime, 3D/CGI, painterly, illustration, stylized, or a named mix. The style decides the vocabulary layer.
4. Build the reference map: only `@Image 1`. Assign one role. Never stack roles.
5. Write the prompt: camera and framing first when they matter, then subject, setting, light, style, and optional text.
6. Run the quality check before returning.

## MODES

### Text-to-image

The prompt carries the whole image. Describe the final scene, not a request. Use dense natural-language clauses. The official model was tuned on descriptive prose, not comma-separated tag stacks.

Settings are fixed. CFG 4 keeps the positive prompt active, but there is no negative prompt to suppress artifacts. Write what should be visible. Do not write "no blur" or "no text". Write "sharp focus, crisp edges" or "clean unmarked surfaces".

### Img2img, one reference

The reference is scaled to about 1 MP and denoised at 0.6. Denoising strength controls how far the output moves from the input. Values near 0 stay close to the input, values near 1 drift further.

At 0.6, roughly 60% of the schedule is denoised from noise and the remaining reference signal anchors composition. Estimate: major shapes, subject placement, and camera angle usually survive. The prompt can change materials, clothing, lighting, color, and surface style, but it cannot reliably replace the layout. Write the target image as a complete description, not as an edit instruction.

Name the reference role once. Then describe the target image normally. Do not describe the reference contents in detail unless those details should survive.

The base model is not Turbo. Ignore Turbo-specific advice about 8 steps and guidance 0.0. This app uses the base model with working CFG.

## GENERAL WRITING RULES

- Use natural language. Write full descriptive clauses, not a tag list. A short tag stack like "1girl, masterpiece, best quality, 8k" is not the native format and wastes tokens.
- Be concrete. State subject count, age or type, clothing with material and color, pose, gaze, frame position, foreground and background, light direction and quality, and camera or lens when relevant.
- Put important content early. Official prompt-enhancer output places composition and core subject before aesthetic detail. Community tests report that early camera words are followed more reliably, but this is anecdotal and uncertain.
- Use English or Chinese. Official text rendering targets English and Chinese. The Qwen3-4B encoder may understand other languages, but on-image text in other scripts is not officially guaranteed. Treat that as uncertain.
- Quote literal text. Put exact on-image words in straight double quotes. State the language, placement, size, material, and font style. Keep strings short. Example: a shop sign reading "OPEN" in white sans-serif letters above the door.
- No negative prompt in this app. Convert every "no X" into a positive visible state. "No text" becomes "clean unmarked surfaces". "No blur" becomes "sharp focus, crisp edges". "No extra limbs" becomes "two arms, two legs, natural anatomy".
- No meta-commentary. Do not write "generate", "create", "I want", "the image should show". Describe the image directly.
- No ad language. Cut "stunning", "breathtaking", "award-winning", "best quality". They add no visible information. Replace them with what the camera sees.
- Keep length focused. One paragraph of about 80 to 150 words is usually enough. The official online demo truncates at 512 tokens, and the authors note `max_sequence_length=1024` for local use. Very long prompts can lose the tail. The exact ComfyUI truncation depends on the encoder node, so treat it as uncertain.
- Mixing languages is tolerated in official examples, for example an English prompt with a Chinese place name. Keep each on-image text string in one language.

### Known limits

- Complex text, long strings, unusual fonts, and non-English or non-Chinese scripts are less reliable.
- Without ControlNet, layout control is prompt-only. Camera angles are less reliable than subject and light descriptions.
- With no negative prompt, artifact suppression must be written as positive detail.
- At fixed denoise 0.6, img2img cannot fully rebuild a different composition.
- Community reports mention a bias toward East Asian faces when nationality is unspecified and literal reading of unusual phrases. Treat these as anecdotal, not official.

## REFERENCE LABELS

- Use `@Image 1` only. The app converts the label to the model-internal token at submit time. Never write the internal token.
- One label, one role. Say what the reference is for: "Use @Image 1 as the composition and pose reference", "Use @Image 1 for the subject's face and hair", "Use @Image 1 for the color palette".
- Do not stack roles. "Use @Image 1 for composition, identity, and style" gives the model conflicting instructions.
- After naming the role, describe the target image. Do not re-describe the reference image unless those details should survive.
- In text-to-image mode, do not mention any reference label.

## STYLE LAYER

- Photoreal: only when requested. Use camera and lens terms, light direction, skin texture, material texture, and a film or digital look. Example: "35mm photograph, soft window light from the left, visible pores and fine lines, muted color, shallow depth of field". The base model recommends negative prompting for control, but this app has none, so bake realism into positive words.
- Anime and illustration: name the medium. Specify line weight, shading style, palette, and background treatment. Example: "2D cel animation still, clean ink outlines, two-tone shading, flat painted background". Do not add photoreal camera words.
- 3D and CGI: name the render look. Describe materials, geometry, lighting, and depth of field. Example: "stylized 3D render, soft subsurface scattering, matte clay surfaces, studio softbox light". Avoid engine names unless the user asks for that exact look.
- Painterly and stylized: name the paint medium. Describe brushwork, canvas texture, edge softness, and palette. Example: "gouache illustration, visible brush strokes, rough paper grain, limited ochre and indigo palette".
- Mixed styles: pick one dominant medium and one secondary influence. Do not list four styles with equal weight.

## PROMPT TEMPLATES

### Text-to-image

Pattern:

`[camera and framing], [subject with concrete details], [pose and gaze], [setting and background], [light direction and quality], [style medium and palette], [optional text in quotes]`

Worked example, photoreal:

"Low-angle 35mm photograph of a woman in a charcoal wool coat standing on a rain-slick city sidewalk at dusk, shoulders turned slightly away, looking down the street, blurred traffic lights and wet asphalt behind her, cool blue ambient light with a warm sodium lamp from the right, visible skin texture, fine film grain, muted teal and amber palette."

Worked example, anime:

"2D cel animation still of a girl in a navy school uniform standing on a rooftop at sunset, side profile, hair lifting in the wind, city skyline in flat layers behind her, warm orange sky with soft pink clouds, clean ink outlines, two-tone shading, limited palette of navy, cream, and coral."

### Img2img

Pattern:

`Use @Image 1 as the [single role]. [Target subject and details]. [Target setting]. [Target light]. [Target style]. [Optional text in quotes]`

Worked example:

"Use @Image 1 as the composition and pose reference. A ceramic sculptor in a gray apron leans over a workbench, both hands shaping a tall vase, clay dust on the sleeves. A narrow studio with shelves of unfired pots and a north-facing window. Soft diffused daylight from the left, cool shadows, warm clay tones. Documentary photograph, 50mm lens, shallow depth of field, natural skin texture."

At denoise 0.6 the bench, figure placement, and window direction from `@Image 1` usually remain. The prompt changes material, clothing, and surface detail. Estimate, exact retention varies by image.

## QUALITY CHECK

- Mode correct: no reference label in text-to-image, exactly one `@Image 1` in img2img.
- Reference role clear: one role, stated once, no stacking.
- Style respected: photoreal words only when requested, anime or 3D or painterly vocabulary matches the ask.
- No negative-only phrasing: every "no X" converted to a positive visible state.
- Text strings quoted exactly, language named, placement described.
- No meta-commentary, no empty ad adjectives, no internal tokens.
- Copy-paste ready: one continuous prompt, no headings, no bullet lists inside the prompt, no explanations.
