---
name: "wan-2-2-director"
description: "Author Wan 2.2 prompts for text-to-video, image-to-video and first-last-frame clips in this app."
---

# Wan 2.2 Director

Style first. Treat the user's style request as a constraint. Read it before anything else. It outranks the model's default look. Photoreal only when the user asks for photoreal, realistic, documentary or live action. For image and first-last-frame modes, the reference frames set the style unless the user asks to change it. Never add a photoreal tag to an anime or illustration frame.

Wan 2.2 uses a different prompt shape for each path. Text-to-video uses `Entity + Scene + Motion`, with optional `Aesthetic control + Stylization`. Image-to-video uses `Motion + Camera movement` because the image already defines the subject, scene and style.

## WORKFLOW

1. Read the inputs: user request, image count, style request, duration and aspect ratio.
2. Detect mode by frame count:
   - 0 images: text-to-video.
   - 1 image: image-to-video, start frame only.
   - 2 images: first-last-frame.
   - 3 or more: stop and ask which two frames are start and end.
3. Detect style:
   - Explicit style wins. "Anime", "3D", "watercolor", "photoreal" are direct orders.
   - No explicit style with 1 or 2 images: preserve the frame style.
   - No explicit style with 0 images: use a neutral cinematic look, not photoreal by default.
   - Two conflicting styles: ask once, then use the first.
4. Build a frame map:
   - T2V: start state, one action path, end state.
   - I2V: what is already true at t=0, what changes, what must stay.
   - FLF: start state, end state, one transition path, what must stay.
5. Write one paragraph in the order below. Use present tense and concrete verbs.
6. Run the quality check. Fix failures before returning the prompt.

## MODES

| Mode | Inputs | Frame roles | Prompt job |
|---|---|---|---|
| Text-to-video | No images | No frame labels | Invent subject, action, setting, camera, light, style |
| Image-to-video | 1 image | `@Image 1` is the start frame | Describe motion and one camera move |
| First-last-frame | 2 images | `@Image 1` is the start, `@Image 2` is the end | Describe the transition and one camera move |

`@Image 1` always means the first frame. `@Image 2` always means the last frame. In image-to-video, `@Image 2` must not appear. In first-last-frame, both labels must be clear and used correctly.

Wan 2.2 T2V, I2V and first-last-frame output is silent. Alibaba lists these Wan 2.2 models as `No audio`. Speech-to-video is a separate model.

## GENERAL WRITING RULES

- Write motion in chronological order. Start at t=0, then the next action, then the end state. Do not describe a montage.
- Use one main action per clip. A short clip can hold one action and one small environmental motion. Wan 2.2 fails on long choreographed sequences.
- Keep action physically possible. Feet stay on the ground unless the user asks for fantasy. Objects have weight. Fabric, hair and water react to motion.
- Use one continuous shot. Cuts happen between clips, not inside a clip. The official guide states one clip equals one continuous shot.
- Use one camera move or `fixed camera`. Do not combine a push-in with a tracking shot and an orbit in the same prompt.
- Preserve what the input frames already show. In I2V and FLF, do not redescribe the face, wardrobe, room or lighting unless it changes. Spend words on motion.
- No meta-commentary. Do not address the model, the viewer or the app. Do not mention resolution, frame count, steps, LoRA, sampler, aspect ratio or render settings.
- No ad language. Drop "cinematic masterpiece", "best quality", "8k", "ultra detailed", "trending", "award-winning", "stunning" and "seamless".
- No audio claims. Do not write dialogue, quotes, music, footsteps, wind sound or sound effects. If a person speaks, describe only visible mouth and body movement.
- Do not rely on exact text. The official guide warns that text renders approximately and specific words will not be precise. Keep signs, labels and subtitles short or omit them.
- Use positive phrasing. Name what is present. Write "clean edges, stable frame, sharp detail" instead of "no blur, no shake". The API has a separate negative field. Do not put negation lists in the prompt text.
- Fit the duration. More events do not fit in a short clip. The app default is 81 frames at 24 fps, 3.375 seconds. Hosted Wan 2.2 is fixed at 5 seconds.

Known limits: exact text is unreliable, lip sync to exact words is unreliable, rapid scene changes fail, very long action sequences fail, and clips longer than the training window lose coherence.

## REFERENCE LABELS

The app converts these labels to the model's internal tokens. Use only the app labels `@Image 1` and `@Image 2`. Never emit internal model tokens, bracket tags, JSON or natural-language image numbering.

Examples:

- `the woman in @Image 1 turns toward the window`
- `the paper boat drifts from @Image 1 and settles against the step in @Image 2`

Use the label when the frame matters. Do not repeat it in every sentence. One clear reference per frame is enough.

## PROMPT STRUCTURE

Recommended order for this app:

1. Style opener. One or two words: `photoreal`, `2D anime`, `3D render`, `watercolor illustration`. Skip it when the frame already carries the style.
2. Subject. Species, age, build, wardrobe, material. Only details that matter. In I2V and FLF, refer to `@Image 1` instead of re-describing the subject.
3. Action. One main action in order. Add one environmental motion if the scene feels dead. Name the end state.
4. Setting. Place, time, weather, background activity. Keep it secondary to the action.
5. Camera. Shot size, angle and one move. Example: `medium close-up, eye level, slow push-in`. If the camera does not move, write `fixed camera`.
6. Light. Source, quality, direction and color. Example: `soft window light from the left, warm tones`.
7. Finish. Medium, texture and grade. Example: `natural skin texture, muted color grade, 35mm film look`.

The official advanced formula groups this as `Entity + Scene + Motion + Aesthetic control + Stylization`. The order above is the same information arranged for a single continuous shot.

Length:

- App default 3.375 seconds: 50 to 100 words, 2 to 4 sentences.
- 5 second target: 80 to 150 words, 3 to 6 sentences.
- Hard ceiling for Wan 2.2 API prompts: 800 characters. Keep the app prompt under 700 characters to leave room for labels.

For 5 seconds, use one action with three beats: start state, visible change, end state. Do not add a second scene.

Camera vocabulary: `extreme wide shot`, `wide shot`, `full shot`, `medium shot`, `close-up`, `extreme close-up`, `low angle`, `high angle`, `aerial shot`, `over-the-shoulder`, `Dutch angle`, `push-in`, `pull-out`, `pan left`, `pan right`, `tilt up`, `tilt down`, `tracking shot`, `orbit`, `crane up`, `fixed camera`.

Light vocabulary: `daylight`, `night`, `dawn`, `sunset`, `overcast light`, `firelight`, `practical light`, `soft light`, `hard light`, `side light`, `backlight`, `rim light`, `top light`, `warm tones`, `cool tones`, `mixed tones`, `high contrast`, `low contrast`.

## STYLE LAYER

Photoreal only when requested. Use `photoreal`, `natural skin texture`, `real lens behavior`, `practical light`, `documentary look`. Avoid `8k`, `hyperreal` and `masterpiece`.

Anime and illustration: use `2D anime`, `cel animation`, `clean line art`, `flat colors`, `limited shading`, `hand-drawn`. Keep motion simple and readable. Do not mix photoreal skin or film grain into a cel-shaded frame.

3D and CGI: use `3D render`, `soft global illumination`, `subsurface scattering`, `clean materials`, `toy-like plastic`, `brushed metal`. Use `Pixar-style` only when the user asks for it. Do not add film grain unless the request is mixed media.

Painterly and stylized: use `oil painting`, `gouache`, `watercolor`, `ink wash`, `visible brushstrokes`, `matte painting`, `paper cutout`, `claymation`. Keep camera moves slow and subjects large. Fast motion smears texture.

Use at most two style tokens. One primary style plus one finish is enough. Conflicting style words produce a muddy frame.

## PROMPT TEMPLATES

### Text-to-video

Skeleton:

`[style]. [subject] [action], then [second beat], ending [end state]. [setting]. [shot size and angle], [camera move]. [light]. [finish].`

Example:

`Photoreal wildlife documentary. A red fox with a thick winter coat trots through a snow-covered birch forest at dawn, snow kicking up behind its paws. It slows, turns its head toward the camera and holds. Wide shot at eye level, slow tracking move. Soft winter daylight, cool shadows, shallow depth of field, natural color grade.`

### Image-to-video

Skeleton:

`[style if changing]. The [subject] in @Image 1 [action], then [second beat], ending [end state]. [camera move]. [light change or preserve]. [finish].`

Example:

`Photoreal. The woman in @Image 1 turns from the window, lifts a ceramic cup and takes a sip, then lowers it. Steam curls past her face. Medium close-up at eye level, slow push-in. Warm morning side light, soft shadows, natural skin texture.`

### First-last-frame

Skeleton:

`[style if changing]. The [subject] in @Image 1 [transition action] and reaches [end state] in @Image 2. [one transition detail]. [camera move]. [light]. [finish].`

Example:

`Photoreal. The paper boat in @Image 1 drifts across the puddle, spins once and settles against the stone step in @Image 2. Ripples spread to the frame edges. Low angle at water level, fixed camera. Overcast daylight, muted colors, wet stone texture.`

When the two frames differ a lot, name the transition mechanism. Use a camera move, a subject move or a light change. The official first-last-frame guide recommends describing the transition when the subject or scene changes significantly.

When the two frames show different people, outfits or styles, the model will interpolate or morph. Describe the intended transformation or ask for consistent frames. Do not promise identity preservation across mismatched frames.

## QUALITY CHECK

- Mode matches the input count.
- `@Image 1` and `@Image 2` are used correctly.
- No internal tokens, bracket tags or JSON.
- Start state matches the input frame.
- End state matches `@Image 2` in first-last-frame mode.
- One main action, physically possible, in chronological order.
- One camera move or `fixed camera`.
- Motion fits the clip length.
- Style request respected. No forced photoreal.
- No audio, dialogue, music or sound effects.
- No exact text reliance.
- No meta-commentary, settings or ad language.
- Positive phrasing only.
- One paragraph, no labels, no explanations, copy-paste ready.
