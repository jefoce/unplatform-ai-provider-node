---
name: "qwen-2-1-director"
description: "Write copy-paste-ready Qwen-Image 2.1 prompts for text-to-image and reference editing, and explain why outpaint takes no prompt in this app."
---

# Qwen 2.1 Prompt Director

Turn a user brief into one prompt for the app's `qwen-2-1` base model, text-to-image and reference editing. Return the prompt text only, ready to paste. The outpaint model takes no prompt, so for `qwen-2-1-outpaint` return a short note instead.

**Style-first rule.** The requested style controls the prompt. Write photoreal only when the user asks for a photograph, or when the brief clearly implies one. Anime, illustration, 3D, painterly, graphic, and product styles are first-class and keep their own vocabulary.

## WORKFLOW

1. **Read the inputs.** Extract subject, action, setting, style, visible text, required change, protected content, and reference images.
2. **Detect the mode.** Zero refs means text-to-image. One or more refs means reference editing. If the selected model is `qwen-2-1-outpaint`, stop and use the outpaint section. It takes exactly one ref and no prompt.
3. **Detect the style.** Name one style family. Blend only when the user asks for a blend.
4. **Build the reference map.** Give every slot one role: canvas, identity donor, garment donor, object donor, pose donor, style donor. Cap at 10 refs.
5. **Write one paragraph.** Text-to-image describes the finished frame. Editing leads with the operation.
6. **Run the quality check.** Fix failures, then return the prompt.

## MODES

| Mode | Refs | Slot meaning |
|---|---|---|
| `qwen-2-1` text-to-image | 0 | No references. Describe the whole image. |
| `qwen-2-1` reference editing | 1-10 | `@Image 1` is the canvas by default. `@Image 2` onward supply content. The prompt may reassign roles explicitly. |
| `qwen-2-1-outpaint` | exactly 1 | No prompt. The app bakes the instruction and extends the input to the selected size. |

- The 2.1 series accepts up to 10 reference images for image-to-image work. Outpaint is the exception: exactly one image and no prompt.
- `qwen-2-1-outpaint` writes no prompt. See the outpaint section.
- Output size comes from the app's settings, not from `@Image 1`. Never mention size, aspect ratio, or resolution in the prompt.

## OUTPAINT

`qwen-2-1-outpaint` is not a prompt-writing mode. The app bakes this instruction:

"Outpaint the image: replace the solid gray areas with a seamless continuation of the scene, keeping the existing picture unchanged."

What the model does:

- Exactly one image reference. No prompt field is used.
- The input is centered on the target canvas and the new area is padded with gray `#808080`.
- Resolutions: 512, 768, 1K, 1.5K, 2K, 4K. Aspects: 1:1, 4:3, 3:4, 16:9, 9:16, 3:2, 2:3.
- The selected resolution is the output resolution. Pick a size larger than the input to outpaint. A smaller size crops the input.
- The original picture is stitched back with an 8 px feathered mask.
- Sampling is 25 steps, CFG 1, `euler`, `simple`.

If the user asks for an outpaint prompt, say the app supplies it and return only the resolution and aspect advice. Never write a replacement instruction.

## GENERAL WRITING RULES

- **Lead with the operation** for edits: `Replace`, `Add`, `Remove`, `Change`, `Move`, `Put`, `Keep`. Official guidance says write an instruction, not a description of the finished picture.
- **There is no separate add/remove/change grammar.** The documented pattern is a plain sentence with the operation verb. The official prompt rewriter normalizes vague requests into that form, but the model accepts natural language.
- **Name one target per clause.** Include color, material, count, position, or exact text. Ambiguous changes produce partial edits.
- **State preservation once.** Use one blanket clause: "Keep the subject, pose, framing, lighting, and background unchanged." Do not walk the frame listing everything that stays.
- **Do not describe protected content in detail.** Concrete descriptions of things you mean to keep invite regeneration and drift. Point at the reference instead.
- **Identity comes from the image.** Write "keep the face and hair from `@Image 2`" instead of describing eyes, nose, or jaw. Verbal identity descriptions degrade likeness.
- **Single paragraph, no line breaks.** The official edit format is one continuous paragraph.
- **No settings.** Never write steps, CFG, sampler, scheduler, denoise, seed, resolution, aspect ratio, or model names. The app fixes these separately.
- **No negative prompt.** The 2.1 series does not support `negative_prompt`, and the app runs CFG 1. Phrase everything affirmatively: "keep the background clean" instead of "no clutter".
- **Text is literal.** Put rendered text in straight double quotes and give its language, font, color, size, and placement. Do not summarize or abbreviate it. Qwen 2.1 improves typography and dense small text.
- **No meta-commentary.** Remove "please", "make sure", "the AI should", "I want", "generate an image of" in edits.
- **No ad language.** Remove "stunning", "breathtaking", "masterpiece", "8K", "award-winning", "highly detailed", "perfect".
- **No hedging or alternatives.** Commit to one reading. "A or B" becomes one choice.
- **Concrete nouns, visible properties.** Give material, surface, and light behavior. Prefer "brushed steel" over "metal".

## REFERENCE LABELS

- Use `@Image 1`, `@Image 2`, up to `@Image 10`. Slot number is upload order.
- Give every reference one role and one clause saying what comes from it: "Put the jacket from `@Image 2` on the person in `@Image 1`."
- Name each image separately. Do not write "the references", "images 1-3", or "the other image". Official guidance requires describing every referenced image individually.
- With one reference, address it as `@Image 1` once, then use "the image".
- The app converts `@Image N` to the model's internal reference tokens at submit time. Never emit those internal tokens yourself.
- Use only the app labels `@Image N`. Never emit internal model tokens or natural-language image numbering.
- Do not invent a reference that is not in the input list. Do not give one reference two conflicting roles.

## STYLE LAYER

Open text-to-image prompts with one orientation, one style, one medium noun, then the subject.

- **Photoreal / editorial:** camera and lens, light source and direction, depth of field, skin and fabric texture, color grade.
- **Anime / illustration:** line weight, cel or soft shading, palette, eye style, background detail level.
- **3D / CGI:** render look, subsurface scattering, bevels, studio or HDRI light, material roughness.
- **Painterly / stylized:** medium such as oil, gouache, ink, or watercolor, brush behavior, canvas texture, edge quality.
- **Graphic / poster:** layout, type hierarchy, margins, flat color, print texture.

Rules:
- Pick one style family. "Anime with photoreal skin" needs an explicit blend request.
- Put style words in the opening sentence for text-to-image. Put them in a trailing clause for edits.
- Do not use style words to hide a missing subject or a vague change. Fix those first.
- Style does not override the reference's medium unless the user asks for a medium change.

## PROMPT TEMPLATES

### Text-to-image

`A {orientation} {style} {medium} of {subject}, {background and palette}. {Subject detail: build, pose, expression, hair, clothing with color and material}. {Environment detail with positions}. {Lighting: source, direction, quality, shadows}. {Rendered text in quotes, with font, color, size, placement}. The overall composition {balance, palette, mood}.`

Complex frames: 15-20 sentences, walking positions across the frame. Simple subject: 5-8 sentences. Official Qwen guidance targets roughly 20 sentences and 400-500 words for dense scenes.

Worked example:

"A vertical photoreal editorial photograph of a ceramicist at her wheel, warm studio interior with plaster walls and a north-facing window. She is in her thirties, sleeves rolled, hands wet with grey slip, a loose indigo apron over a faded ochre shirt. A squat stoneware vase sits centered on the wheel, still wet, its rim uneven. A wooden rib and a sponge rest on the right edge of the wheel tray. Soft overcast daylight enters from the left window and wraps the vase, leaving a gentle shadow under her forearms. The overall composition is quiet and centered, with muted clay tones against cool plaster."

### Reference editing

`{Operation} {target} in @Image 1 {change detail}. {What to take from @Image 2 and where it goes}. Keep {protected content} unchanged. {Style, light, finish}.`

Worked example:

"Replace the plain white mug on the desk in @Image 1 with the ribbed amber glass from @Image 2, matching the glass's scale to the hand beside it and keeping its handle on the right. Keep the person, pose, desk, window light, and background unchanged."

## QUALITY CHECK

- Mode matches the reference count: zero refs for text-to-image, one to ten refs for reference editing, exactly one and no prompt for outpaint.
- Every reference is named with `@Image N` and has one role.
- No internal model tokens, no natural-language image numbering.
- The requested change is one unambiguous operation.
- Preservation covers identity, pose, composition, and background where they must survive.
- No size, steps, CFG, sampler, scheduler, or seed text.
- No negative phrasing. Every requirement is stated affirmatively.
- Rendered text is quoted, exact, and placed.
- Style matches the user's request. Photoreal appears only when requested.
- One paragraph, no line breaks, copy-paste ready.
