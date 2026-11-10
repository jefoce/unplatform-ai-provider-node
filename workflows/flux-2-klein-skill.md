---
name: "flux-2-klein-director"
description: "Write copy-paste FLUX.2 Klein prompts for text-to-image and up to four-reference editing, led by the requested style and the optional Lenovo LoRA trigger."
---

# FLUX.2 Klein Prompt Director

Treat style as a decision. Read the requested style before writing. Photorealism is one option. Anime, illustration, 3D/CGI, and painterly looks are equally valid. Do not default to a photographic look when the user asks for something else.

Model context: `flux-2-klein` runs text-to-image and multi-reference editing with up to 4 image refs. The flow uses 4 steps, CFG 1, euler, Flux2Scheduler, and no negative prompt. References are scaled to about 1 MP and applied to the positive branch. The negative branch is zeroed. Prompt wording is the main control surface.

Known limits: no prompt upsampling, no negative prompt, max 4 refs, semantic reference matching rather than pixel-perfect copying, and text that can distort. Write the detail yourself.

## WORKFLOW

1. Read the inputs. Collect the user request, the style, the number of references, any text to render, and whether the Lenovo LoRA is active.
2. Detect text versus reference mode. No refs means text-to-image. One ref means single-reference edit. Two to four refs means multi-reference composition. If the prompt must render text, note the exact string, placement, font, and color.
3. Detect the style. Choose one primary style: photoreal, anime/illustration, 3D/CGI, or painterly/stylized. If the user names a style, use it. If not, infer from the subject and refs. Do not default to photoreal.
4. Build the reference map. Give each provided reference one primary role. Name the role and the content: "the woman in @Image 1", "the coat in @Image 2". Every provided reference conditions the output. If a reference is not needed, remove it before generation.
5. Write the prompt. Lead with the subject or the main edit. Add action, setting, light, style, and only the details that matter. Use positive language. For edits, add one sentence that lists what must stay unchanged.
6. Run the quality check. Verify mode, labels, roles, identity, change clarity, style, text, and copy-paste readiness.

## MODES

### Text-to-image

No reference labels. Write a complete scene. Put the subject and action first. Add setting, light, medium, and a few concrete details. Typical length is 40 to 80 words. Complex scenes can run longer. Klein has no prompt upsampling, so every detail you need must be in the prompt.

### Single-reference edit

One label: `@Image 1`. The reference is both the source and the target. State the change first, then the preservation list. Do not redescribe the whole image. Describe only the new state and what must survive.

Example shape: "Change X in @Image 1 to Y. Keep A, B, and C unchanged."

### Multi-reference composition

Two to four labels. Each slot gets one primary role. Compose the output scene, then map each reference to its contribution. Use explicit labels plus content names. Keep the roles distinct. If one reference must supply two things, name the primary role and one secondary detail in the same clause. Do not give one slot two conflicting jobs.

Up to 4 refs are supported. More refs increase ambiguity and VRAM use. If a ref is not needed, remove it.

Reference slots can control:

- `@Image 1`: primary subject, face and identity, or the base scene.
- `@Image 2`: second subject, garment, product, or style anchor.
- `@Image 3`: pose, body shape, layout, composition, or an additional object.
- `@Image 4`: background, environment, lighting, or a final style anchor.

Treat these as roles. They are not fixed rules. A slot can hold a different role if the map stays clear. One primary role per slot.

Reference behavior notes:

- The app scales each reference to about 1 MP. Fine print, tiny logos, and micro-text can lose detail. Restate critical text in the prompt.
- References condition the positive branch. The negative branch is zeroed. There is no "avoid this image" slot and no negative reference. Use positive instructions only.
- The model interprets references semantically. It does not copy pixels exactly. For identity, name stable features: face shape, eyes, hairline, glasses, scars, jewelry. For products, name material, color, logo placement, and stitching. Expect drift on small details.

## GENERAL WRITING RULES

- Write natural language. Avoid tag soup. Klein responds best to narrative prose. Use short paragraphs or clear sentences. Comma-separated keyword piles lose relationships.
- Put the most important element first. Word order matters. The model pays more attention to what comes first. Lead with the subject or the main edit.
- Be concrete. Name the material, color, shape, texture, spatial relationship, light direction, and camera or medium. "A chipped enamel mug" beats "a nice mug".
- Describe the desired state. Do not list exclusions. There is no negative prompt. "An empty street" works. "No people" does not. At CFG 1 there is no separate negative branch to act on.
- For edits, separate change from preservation. One clear change sentence. One clear preservation sentence. Name the face, hair, pose, framing, light, logo, and text that must survive.
- Do not write meta-commentary. No "generate an image of", "please", "make it look good", "high quality", "masterpiece", or "8k". Describe the image itself.
- Do not write ad copy. No "stunning", "breathtaking", "revolutionary", or "must-see". Name the visual quality instead: "soft window light", "matte black ceramic", "visible brushwork".
- Keep one primary aesthetic. Do not ask for a photo and a watercolor in the same prompt unless the user asks for deliberate mixed media. If mixed, name the dominant medium and the accent.
- Quote text that must render. Put the exact string in double quotes. State placement, font style, size, and color. Keep strings short. Verify the output, because text can distort.
- Use hex codes for exact color when the user provides them. Attach the code to the object: "the jacket in color #1B3A2F". Do not scatter codes without an object.
- Avoid weight syntax like `(word:1.3)`. It is not documented for FLUX.2. Use word order and specific nouns instead. This is practical guidance, not an official parameter.
- No prompt upsampling. If the scene needs a detail, write it. Do not rely on the model to invent missing composition or lighting.

## REFERENCE LABELS

Use the app labels exactly: `@Image 1`, `@Image 2`, `@Image 3`, `@Image 4`.

- One label per reference. Do not invent labels for refs that were not provided.
- Pair every label with a content name. "The woman in @Image 1" is better than "@Image 1" alone. This keeps the instruction readable and helps the model bind the right element.
- Keep the label order stable across the prompt. Do not call the same ref by two different labels.
- The app converts `@Image N` to the model-internal reference form. Never emit that internal form, raw reference payloads, base64, JSON, or token syntax. Write only the app labels.
- Use one primary role per slot. Do not ask `@Image 1` to be both the face and the background if another slot can carry one of them.
- Mention every provided reference. If a ref is not wanted, remove it before generation. An unmentioned ref still conditions the output.
- There is no negative reference. Do not write "ignore @Image 2" or "not like @Image 3". Use a positive instruction and, if needed, remove the ref.

Optional map line before the scene:

```text
@Image 1: face and identity. @Image 2: coat. @Image 3: pose. @Image 4: lobby.
```

Then write the scene in prose. The map line is optional. The prose must still stand alone.

## LENOVO LORA

The flow may load `lenovo_flux_klein9b` at strength 0.6. Its trigger is `l3n0v0`. A third-party guide describes it as a realism LoRA for Klein 9B that adds film-like color, grain, and believable light. That description is not official BFL documentation.

Include the trigger when:

- The LoRA is loaded and active.
- The requested output is photographic realism, including portrait, documentary, film, or natural-light photography.
- The reference edit is a photographic scene and the goal is a realistic result.

Add it once at the start, followed by a comma:

```text
l3n0v0, A ...
```

Do not include the trigger when:

- The LoRA is not loaded.
- The user asks for anime, illustration, 3D/CGI, graphic design, poster art, or painterly output. A realism LoRA pulls the render toward film and fights those styles.
- The user explicitly says no LoRA or asks for a clean, untextured render.
- The prompt is for a flat graphic, exact brand layout, or text-heavy design where film grain and photographic light would hurt the result.

If the LoRA is fixed on and the style is non-photographic, leave the trigger out and state the medium strongly. Expect some photographic bias. If the app allows disabling the LoRA, disable it for that request.

Do not repeat the trigger, translate it, explain it, or invent other LoRA names or weights. The trigger is not a subject or a style word. Keep it at the front, then write the scene. Do not use it as a substitute for photographic detail. Still describe light, lens, and texture.

## STYLE LAYER

Pick one primary style from the user request. Use the vocabulary of that medium. Do not borrow terms from another medium.

### Photoreal

Only when requested. Name the capture: camera, lens, film stock, light direction, grain, skin texture, depth of field. Use a real reference like "Kodak Portra 400" or "35mm, f/2". Avoid generic "photorealistic" as the only style word. If the user asks for a phone snapshot, name that look: "early digital camera, slight noise, direct flash". If the user asks for clean commercial work, say "studio softbox, neutral background, sharp product detail".

### Anime and illustration

Name the medium and lineage: "2D cel animation", "manga ink", "flat color", "clean line art", "limited palette". Describe line weight, shading, and color. Do not use lens, film grain, or camera terms. If the user wants a specific era, name it: "1990s TV anime", "watercolor picture book".

### 3D and CGI

Name the render look: "stylized 3D render", "matte clay materials", "subsurface scattering", "soft global illumination", "clean studio light". Describe material response and shape. Do not use film grain unless requested. Do not call it a photo.

### Painterly and stylized

Name the medium and mark: "oil on canvas", "gouache", "impasto", "visible brushwork", "canvas texture", "limited palette". Describe edge quality and color handling. Do not use camera or lens terms. For graphic or print looks, name the process: "screen print", "risograph", "halftone".

If a reference carries the style, say "match the medium and palette of @Image N" and keep the rest of the prompt consistent with that medium. One primary aesthetic. Mixed media only when requested. Then name the dominant medium and the secondary accent.

## PROMPT TEMPLATES

### Text-to-image

Template:

```text
[trigger,] [subject and action]. [setting and light]. [style and capture details]. [secondary details].
```

Worked example with the LoRA active:

```text
l3n0v0, A young ceramicist shapes a tall vase on a kick wheel in a sunlit studio. Clay dust hangs in the warm window light. Shot on Kodak Portra 400, 50mm lens, shallow depth of field, natural skin texture, quiet documentary mood.
```

Drop `l3n0v0,` when the LoRA is off or the style is not photographic.

### Single-reference edit

Template:

```text
Change [target] in @Image 1 to [new state]. Keep [face, hair, pose, framing, light, details] unchanged. [style and capture details].
```

Worked example:

```text
Change the sneakers in @Image 1 to worn brown leather boots. Keep the person's face, hair, pose, blue jeans, the concrete steps, and the overcast light unchanged. Photographic, 35mm lens, natural color, slight grain.
```

### Multi-reference composition

Template:

```text
[Output scene] using the [role] from @Image 1, the [role] from @Image 2, the [role] from @Image 3, and the [role] from @Image 4. Keep [identity and key details] unchanged. Match [light and perspective]. [style].
```

Worked example:

```text
A medium shot of the woman from @Image 1 standing in the hotel lobby from @Image 2, wearing the black coat from @Image 3, posed like @Image 4. Keep her exact face, shoulder-length hair, and the coat's silver buttons. Match the warm chandelier light and the lobby's marble perspective. Photographic, 50mm lens, natural skin texture.
```

Use only the labels that match the provided refs. For two refs, drop `@Image 3` and `@Image 4`. For three, drop `@Image 4`.

## QUALITY CHECK

- Mode matches the reference count: zero refs for text-to-image, one for a single edit, two to four for composition.
- Every provided reference has one label and one primary role. No unused refs, no invented labels.
- Each label is paired with a content name. The label order is stable.
- Identity details are named: face, hair, body, distinguishing marks, jewelry, glasses.
- The change is unambiguous. One main change. The preservation list names what must stay.
- The style is respected. The vocabulary matches the requested medium. No photo terms in anime, 3D, or painterly prompts.
- No negative wording. Exclusions are rewritten as positive descriptions.
- No meta-commentary, no ad language, no generic quality words.
- Any rendered text is quoted, short, placed, and styled. Critical text is restated even when a ref contains it.
- The LoRA trigger is present only for photographic work with the LoRA active. It is absent for non-photographic styles.
- The prompt is copy-paste ready. No notes, no placeholders, no internal tokens, no raw reference data.
- Length fits the task. Roughly 40 to 80 words for a single scene. Longer only when multi-ref detail requires it.
