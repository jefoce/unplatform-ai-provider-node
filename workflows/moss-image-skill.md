---
name: "moss-image-director"
description: "Author copy-paste MOSS Image prompts for this app: style-first captions, one @Image 1 reference role, text-to-image, single-reference img2img, and depth-controlled pose."
---

# MOSS Image Director

Write the prompt the user actually asked for. Their style wins. Photoreal is one option, never the default.

MOSS Image is a 5B single-stream DiT from OpenMOSS with a Qwen3.5-9B text encoder. It was trained on long, detailed captions, so prompts read like careful image descriptions, not command lists. It renders English and Chinese text well, accepts prompts up to roughly 4K tokens, and works across photoreal, anime, 3D, and illustrated styles.

This skill covers the app's three modes: text-to-image, one img2img reference, and depth-controlled pose. It does not cover JSON layout prompts, because this app does not expose layout boxes.

## WORKFLOW

Follow these steps in order.

1. **Read the inputs.** Extract the subject, action, setting, requested style, visible text, reference image, and any aspect or framing request. Separate what the user shows from what they only describe.
2. **Detect the mode.** No reference means text-to-image. One reference means img2img. One pose or depth reference with the Pose model means pose. Two or more references are out of scope for this app. Ask which single reference to use, or pick the one the user describes as primary.
3. **Detect the style.** Name it: photoreal, anime/illustration, 3D/CGI, painterly/stylized, or a named mix. Use explicit cues from the user. If absent, infer from subject and medium cues, but do not silently default to photoreal.
4. **Build the reference map.** For img2img, assign `@Image 1` exactly one role. Decide what must survive and what may change. Keep that split consistent through the prompt.
5. **Write.** One coherent caption in the detected style. Move through subject and action, appearance and material, setting and composition, light and palette, medium and style, then any visible text.
6. **Quality check.** Run the checklist at the end before returning.

## MODES

### Text-to-image

No reference. The prompt carries all composition, style, and content. Describe the finished frame directly. The model has no memory of prior turns and no external context.

### Pose with one reference

Model `moss-image-pose`. Image reference 1 is a pose or depth source, label `@Image 1`. A depth preprocessor estimates a depth map and the `moss-control` LoRA applies it. There is no mask, and the full depth map applies.

The prompt describes the target image, not the edit. Write the subject, wardrobe, setting, composition, light and style you want. `@Image 1` controls body pose and depth, not face, hair, clothing or color. If the user wants the same person, describe that person explicitly instead of asking the model to copy the reference. Do not describe the depth map, the preprocessor, or the LoRA. Do not ask for a new pose that the reference does not contain.

| File | Folder | Size | Credit |
|---|---|---|---|
| `moss-control.safetensors` | `models/loras` | 298.6 MiB (313,063,368 bytes) | `darask0/MOSS-Image-color-depth-control` |

### Img2img with one reference

The app scales the reference to the generation settings, encodes it, and runs the sampler at denoise 0.6. The reference is a latent starting point, not a model-native image condition. Official MOSS-Image has no image input, so this is ordinary latent img2img, not reference-based generation.

What denoise 0.6 means for the prompt:

- About 40 percent of the reference's latent signal survives the first step. Composition, silhouette, camera angle, and the broad palette usually hold.
- Fine texture, small details, and exact edges are redrawn. The prompt controls style, materials, lighting, surface detail, and moderate content changes.
- The last 60 percent of the 50-step schedule runs, so expect less refinement than a full text-to-image pass.
- Do not ask for a new pose, new camera, or new layout at 0.6 unless the user accepts drift. Describe the reference's pose and framing as facts the image should keep.
- Put the change in the foreground of the sentence. State what stays unchanged in the same breath. Vague edits give the model too much freedom.

If the exact img2img implementation differs in a future app build, the prompt rule stays the same: describe the target image, not the edit operation.

## GENERAL WRITING RULES

**Write captions, not requests.** Say what the picture looks like. "A weathered fisherman mends a net on a wooden dock at dawn" beats "make an image of a fisherman". The official enhancer follows the same rule.

**Natural language first.** Use prose paragraphs. The model supports natural language, tag sequences, and JSON layouts, but this app passes the prompt unchanged, so prose gives the most control. Use tags only when the user supplies tags or explicitly asks for a booru-style anime result. If you use tags, follow the official order: quality, score, meta, year, character, series, artist, general.

**Concrete detail beats decoration.** Name materials, colors, counts, light direction, surface wear, lens, distance, and expression. Specificity is what the model rewards. Do not pad with empty quality words.

**Length.** 60 to 150 words is the normal sweet spot. Use 20 to 40 words only for loose exploration. Use 150 to 400 words for posters, infographics, whiteboards, and text-heavy scenes. Long prompts do not degrade this model, and the encoder handles roughly 4K tokens.

**Bilingual behavior.** Write descriptive prose in English unless the user asks for another language. English has the most training data, and Chinese is also supported. Keep any text that must appear in the image in its original language, verbatim. Never translate, romanize, or "fix" it. Other scripts beyond English and Chinese are uncertain.

**Text rendering.** Put the exact string in double quotes. Insert real line breaks where lines should break. Describe placement, alignment, size hierarchy, font style, color, and the surface it sits on. Automatic wrapping may not land where you want it, so control breaks yourself. Small handwriting is the weakest case, so keep each line short when exact spelling matters.

**No negative prompt in this app.** The SFT card defaults to an empty negative prompt, so this app's behavior is normal for SFT. The official guide's short negative tags are for MOSS-Image-Base. Because no negative branch steers the prompt, phrase everything positively. Do not write "no watermark" or "no blur" and expect suppression. Describe a clean surface, sharp focus, and the intended content instead.

**No meta-commentary.** Remove "please", "generate", "I want", "as an AI", parameter talk, seeds, model names, and workflow notes. Remove "8k, masterpiece, best quality, ultra detailed" stacks unless the user asked for tag style.

**No ad language.** Remove "stunning", "breathtaking", "unleash", "elevate", "seamless", "game-changing". Describe the image, not its marketing copy.

**Do not explain the prompt.** Return only the caption. No preface, no style rationale, no settings recap.

## REFERENCE LABELS

- Use `@Image 1` only. One reference, one role.
- Valid roles: subject identity, face and hair, outfit, product shape, pose, composition and palette, or style. Pick one primary role. A second role is allowed only when the user clearly asks for it, and it must not conflict.
- In pose mode the only valid role is pose and depth. Do not claim that the reference supplies identity, clothing or color.
- State the role in natural language inside the caption. Example: "The woman in `@Image 1` keeps her face, hair, and red jacket; the scene changes to a rain-soaked neon street."
- Use only the app label `@Image 1`. Never emit internal model tokens or natural-language image numbering. The app converts `@Image 1` under the hood.
- Never invent `@Image 2`. Never use `@Video` or `@Audio` with this model.
- Text-to-image prompts contain no reference label.

## STYLE LAYER

Name the medium explicitly in every prompt. One dominant style, at most one accent.

**Photoreal, only when requested.**
Camera and lens, aperture or depth of field, light source and direction, time of day, skin and fabric texture, film stock or digital look. One realistic imperfection helps: worn paint, dust, slight motion blur. Avoid "hyperrealistic" and "8k".

**Anime and illustration.**
Name the lineage: cel-shaded anime key visual, 90s OVA still, flat vector poster, line art with watercolor wash, manga panel. Specify line weight, shading model, palette, and background treatment. Avoid mixing render engines into this style.

**3D and CGI.**
Name the look: matte clay render, glossy toy render, stylized game asset, architectural visualization, soft-body character render. Specify material roughness, subsurface scattering, studio or HDRI lighting, and camera projection. Use "3D render" only when the user wants that look.

**Painterly and stylized.**
Name the medium: oil, gouache, ink wash, pencil, risograph, screen print, paper cut. Describe brush behavior, canvas or paper texture, edge softness, and palette limits. Stylization is a deliberate choice.

**Mixed requests.**
Keep the user's dominant style and add one controlled accent, such as "photoreal street scene with hand-painted signage". Do not blend three mediums.

SFT is the instruction-tuned checkpoint in this app. It produces cleaner text grouping and a more organized layout than Base. Some community notes say SFT can drift toward airbrushed faces on very short character prompts. That claim is unofficial and should be treated as uncertain.

## PROMPT TEMPLATES

Replace every bracketed slot. Never ship brackets or placeholder text.

### Text-to-image

```text
[Medium and style sentence naming the dominant look.] [Subject and action, with age, expression, wardrobe, and material detail.] [Setting with two or three concrete environmental details.] [Composition and camera: shot size, angle, subject placement, foreground and background.] [Lighting and palette: source, direction, quality, time of day, dominant and accent colors.] [Optional visible text: exact string in double quotes, typography, placement, size, color, surface.]
```

Worked example:

```text
A flat screen-printed travel poster in muted cream, terracotta, and deep teal. A red pagoda stands among maple trees before a pale sun and layered blue mountains. The composition is centered and vertical, with generous margins and subtle paper grain. At the top, large bold cream uppercase letters read "KYOTO". Below the artwork, smaller dark teal text reads "AUTUMN LANTERN FESTIVAL", and on the next line in red "November 3 - 9, 2026".
```

### Pose

```text
[Medium and style sentence.] [Subject, wardrobe and expression, described from scratch.] [Setting.] [Pose and body angle taken from @Image 1, plus the camera and framing.] [Lighting and palette.] [Optional visible text.]
```

Worked example:

```text
A soft 3D character render in warm clay materials and muted earth colors. A stocky baker in a flour-dusted apron leans forward with both hands on a wooden counter, shoulders level and feet apart. The bakery interior has tiled walls, a copper oven and a window full of morning light. Take the lean and the arm placement from @Image 1, and keep the camera at chest height with the subject centered. Warm side light from the left, soft shadows, cream and terracotta palette.
```

The pose reference must match the requested pose. Do not ask the prompt to bend the body into a pose the reference does not show.

### Img2img

```text
[Reference role sentence: what @Image 1 supplies and what must stay.] [Target style and medium.] [What changes: subject details, wardrobe, materials, setting, lighting, palette.] [Composition and framing statement consistent with the reference.] [Optional visible text: exact string in double quotes, typography, placement.]
```

Worked example:

```text
The woman in @Image 1 keeps her face, dark bob haircut, pose, and three-quarter framing. Restyle the scene as a cel-shaded anime key visual with clean line work and flat shadow shapes. Her red wool coat becomes a glossy crimson rain jacket, and the plain street becomes a rain-soaked alley with neon signs and wet reflections. Keep the camera at chest height and the subject centered. A vertical sign behind her reads "OPEN LATE" in small white neon letters.
```

For img2img, put the preserved facts before the changes. Put the largest visual change early in the sentence. Keep the reference's geometry as a stated constraint, not a suggestion.

## QUALITY CHECK

Before returning, verify:

- Mode is correct. No reference means no `@Image 1`. One reference means exactly one `@Image 1`. In pose mode, `@Image 1` supplies pose and depth only, and the prompt describes the person and scene.
- Reference role is explicit and singular. Preserve and change lists do not contradict each other.
- Style is the user's style, not a default. The medium is named. Photoreal appears only when requested or clearly implied.
- The caption describes a visible image, with no request verbs, settings, seeds, or model talk.
- Visible text is quoted exactly, keeps its original language and line breaks, and has placement and typography.
- No negative phrasing that depends on a negative prompt. No watermark or blur suppression language.
- No adjectives that only sell the image. No "masterpiece" stacks unless tag style was requested.
- No internal reference tokens. Only `@Image 1` if a reference exists.
- Copy-paste ready: no brackets, no placeholders, no notes, no explanation around the prompt.

Uncertain: exact img2img latent handling in this app's build, how strongly the depth map constrains identity in pose mode, behavior of scripts other than English and Chinese, and the unofficial claim about SFT face styling on short prompts.
