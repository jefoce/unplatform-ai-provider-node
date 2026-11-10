---
name: "ltx-2-5-director"
description: "Author copy-paste LTX 2.5 prompts for text-to-video, image-to-video, and first-last-frame video with native audio, dialogue, and camera direction."
---

# LTX 2.5 Director

Prompt handbook for the app model `ltx-2-5`. LTX 2.5 generates picture and sound in one pass. The prompt is the only creative control this skill writes. Settings, samplers, frame count, and model files are fixed by the app.

## Core Rule: Style First

Write in the style the user asked for. Photoreal is one option, not the default. Anime, illustration, 3D, painterly, and stylized all use the same structure. Only the visual vocabulary changes. If the user gives no style, infer it from the subject and reference frames. Never add "photorealistic" to a request for animation, and never add "anime" to a request for live action.

LTX responds to cinematic prose, not tag lists. No weight brackets, no quality tails, no section labels, no model-specific audio tags.

## WORKFLOW

1. **Read inputs.** Collect the user request, the reference frames, and any dialogue, music, or sound direction.
2. **Detect mode by frame count.** Zero reference frames means text-to-video. One means image-to-video with a start frame. Two means first-last-frame video. Never guess the mode from wording alone.
3. **Detect style.** Name the requested style in one or two words. If absent, use the style visible in the reference frames. If still absent, use neutral cinematic live action.
4. **Build the frame map.** For the app default of 121 frames at 24 fps, the clip runs about 5.04 seconds. Assign beats: opening state, main action, settling end. For first-last-frame, the last beat must land on `@Image 2`.
5. **Write the prompt.** Use the section order in this document. One flowing paragraph. Present tense. One action beat and one camera move.
6. **Run the quality check.** Fix mode errors, frame-role errors, over-long motion, missing audio, and style drift before returning.

## MODES

### Text-to-Video

No reference frames. Describe the entire shot from its first frame. The model invents subject, setting, and motion from the prompt.

### Image-to-Video, One Start Frame

One reference frame, `@Image 1`. It is the first frame. Describe only what happens after it. Do not re-describe the face, clothing, room, or lighting already visible unless the action changes them. Anchor the continuation in natural language, for example: "Using the provided start image as the first frame, the camera slowly pushes in as she turns her head." The model preserves the source identity and composition.

### First-Last-Frame Video

Two reference frames. `@Image 1` is the first frame. `@Image 2` is the last frame. Describe the motion and camera path that connects them. The model interpolates between both images. Keep both frames the same aspect ratio. Do not describe a cut. Do not describe a new location. The transition must be physically reachable in about five seconds.

## GENERAL WRITING RULES

- Write chronological motion. Start at the first frame, move forward, end on a stable state.
- Use present-tense verbs that do something: walks, turns, lifts, exhales, reaches, sets down.
- Keep motion physically possible and simple. One action beat per five seconds. Complex choreography and chaotic physics produce artifacts.
- Use one camera move per shot. Name it, name its direction, and name where it settles.
- Preserve identity in image modes. Repeat the same identifiers for the subject, wardrobe, and location across the paragraph.
- Express emotion through physical cues. Write "her jaw tightens and she looks away" instead of "she is anxious."
- Keep one light logic. One key source, one direction, one color palette. Mixed unexplained sources muddy the result.
- Keep the frame uncrowded. One main subject, at most one secondary figure in soft background.
- No meta-commentary. Never write "this video shows", "generate a clip", "the camera captures the scene", or "a prompt for".
- No ad language. Drop "stunning", "breathtaking", "epic", "masterpiece", "8K", "best quality". Describe the visible cause instead.
- No negative instructions inside the prompt. Put exclusions in the app's negative prompt field if one is exposed. Inside prose, state the positive state you want.
- No shot lists, numbered beats, or section headers. A short screenplay style is allowed only when the scene has dialogue or multiple timed beats.

## REFERENCE LABELS

- Use `@Image 1` and `@Image 2` exactly. These are app-ready labels.
- `@Image 1`: start frame in image-to-video, first frame in first-last-frame.
- `@Image 2`: last frame in first-last-frame only. It has no meaning in text-to-video or single-frame image-to-video.
- Never emit internal model tokens, angle-bracket placeholders, base64, file paths or node names. The app converts labels to model-internal tokens under the hood.
- Never emit `@Video`, `@Audio`, or `@Image 0`. This skill handles image frames only.
- Do not explain the label system inside the prompt. Labels are instructions, not prose.

## PROMPT STRUCTURE

Lightricks lists six elements in this order: shot, scene, action, character, camera, audio. LTX also responds well when the action leads. Use this practical order for a five-second single shot:

1. **Shot and action.** One sentence. Shot scale, subject, and the main action. Example: "A medium close-up of a woman in a green apron setting a ceramic cup on a wooden counter."
2. **Scene and light.** One or two sentences. Location, time of day, light source and direction, palette, texture, atmosphere.
3. **Character.** One sentence. Age, hair, clothing, one distinguishing feature, physical emotion cue. Skip if no person is present.
4. **Camera.** One sentence. One move, relative to the subject, plus the final framing.
5. **Audio.** One or two sentences. Ambience bed, foley tied to the action, optional music, optional quoted dialogue.
6. **Optional style marker.** Fold into sentence one or two. Do not add a separate style paragraph.

Length targets for five seconds:

- One paragraph, 4 to 8 sentences.
- Roughly 70 to 130 words. Longer prompts dilute motion in a short clip.
- One action beat, one camera move, two or three sound sources.
- One spoken line of about 8 to 12 words, with a beat of silence at each end. The rate of about 2.5 spoken words per second is a third-party estimate and should be treated as uncertain.
- For a dialogue-free shot, keep the audio sentence short and concrete.

Do not force every prompt into all six slots. A landscape shot needs no character sentence. An empty room needs no dialogue.

## AUDIO AND DIALOGUE

LTX 2.5 has no special audio tag syntax. Audio is prompted in plain natural language inside the same paragraph as the picture. Dialogue goes in quotation marks. There are no `[sound]`, `SFX:` or `Music:` tags in the official open-source prompting guide.

### Diegetic sound

Name an ambient bed that sets the space, then foley tied to the visible action. Attach each effect to its cause.

- Weak: "Beach sounds."
- Strong: "The wash and pull of small waves, the crunch of her footsteps in wet sand, distant gull calls, and a light sea breeze."
- Add "no music" when the final clip will be scored later. Without it, the model may invent a score.

### Music

Name genre, tempo, and instrumentation only when the scene calls for music. Keep it consistent with the setting. State whether it continues, drops, or changes across the clip.

### Speech

Use this pattern:

`[Speaker] says, in [language/accent] and [delivery], "[exact line]."`

Example: "The barista looks toward the lens and says, in a warm American accent, 'Your order is ready.'"

Rules:

- Quote the exact words. The model speaks the line and lip-syncs it.
- Name language and accent when they matter.
- Direct delivery with a physical or tonal cue: "low and measured", "an excited near-shout", "a whisper". Not a bare emotion label.
- One speaker per line. Keep the face visible and the camera stable during speech.
- Keep the line short enough for the runtime. Long lines get clipped or rushed.
- For singing, write "she sings" and put the lyric in quotation marks.
- Do not ask for a sound with no visible or implied cause.

### Mix

Order the audio sentence by importance: voice first, action effects second, ambience third. Use volume words such as "whisper", "distant", "loud", "muffled" to set levels. Unnamed audio lets the model choose the soundtrack for you.

## STYLE LAYER

Write one style statement. Do not stack contradictory styles.

- **Photoreal, only when requested.** Name the capture language: lens, film stock, light quality, grain. Example: "Shot on a 50mm lens, soft window light, fine film grain, muted color grade."
- **Anime and illustration.** Name the medium and line quality: "2D cel animation, clean ink lines, flat cel shading, limited palette." Keep motion physical and simple. Do not add lens or film-stock language.
- **3D and CGI.** Name the render language: "stylized 3D animation, soft global illumination, matte clay materials, rounded forms." Avoid photoreal skin and film grain cues.
- **Painterly and stylized.** Name the surface: "oil-painted texture, visible brushwork, warm earth palette, soft edges." Keep lighting readable even when the surface is abstract.
- **Neutral live action.** Use plain cinematic terms with no style brand: "documentary-style handheld, natural light, realistic color."

The style word belongs early. It shapes the whole render, not a finishing pass.

## PROMPT TEMPLATES

### Text-to-Video

Pattern: shot and action, scene and light, character, camera, audio.

> A medium wide shot of a fisherman in a yellow raincoat hauling a rope from a wooden dock before dawn. Cold blue light rises from the horizon, a single lamp on the dock casts warm light across wet planks, and mist sits on the water. His hands are red from the cold and his jaw is set. The camera tracks slowly alongside him as the rope comes hand over hand. The soundscape is close: rope creaking through wet palms, water lapping at the pilings, a distant gull, no music.

### Image-to-Video

Pattern: anchor the start frame, describe only the continuation, preserve identity, one camera move, audio.

> Using `@Image 1` as the first frame, the woman in the grey coat turns from the window and walks toward the table. Morning light from the window stays on her left side, the same warm interior and the same grey coat. She sets a cup down and exhales. The camera pushes in slowly and settles on her face. Room tone, the soft clink of ceramic on wood, a quiet radiator hum, no music.

### First-Last-Frame

Pattern: connect `@Image 1` to `@Image 2` with one continuous action and one camera path. Match the final pose to the last frame.

> The shot begins on `@Image 1`, a robot hand open against a dark workshop wall, and ends on `@Image 2`, the same hand closed around a glowing energy cell. The hand rotates toward the cell, fingers curl one by one, and the glow rises across the metal palm. The camera pushes in slowly and settles on the closed hand. Low electrical hum, a soft servo whir, a single metallic click at the close, no music.

## QUALITY CHECK

Before returning a prompt, verify:

- **Mode.** Frame count matches the mode. Zero frames for text-to-video, one for image-to-video, two for first-last-frame.
- **Frame roles.** `@Image 1` is the start. `@Image 2` is the end. No internal tokens or invented labels appear.
- **Motion budget.** One action beat and one camera move fit inside about five seconds. The end state is reachable.
- **Preservation.** Image modes keep identity, wardrobe, location, and light from the reference frames. The prompt does not redesign what is already visible.
- **Audio.** An ambience bed, action-linked foley, and an explicit music choice or "no music" are present. Dialogue is quoted, attributed, short, and single-speaker.
- **Style.** The requested style is stated once and not contradicted. Photoreal appears only when requested.
- **Language.** Present tense, chronological, physical cues, no meta-commentary, no adjectives without a visible cause.
- **Format.** One flowing paragraph, no tags, no headers, no weights, no negative phrasing. Copy-paste ready as written.

## Known Limits

- On-screen text is improved in LTX 2.5 but exact spelling and consistency across frames are not guaranteed. Keep text short, prominent, and verify it. Add critical titles and logos in post.
- Highly chaotic motion can introduce artifacts. Simpler, plausible motion is more reliable.
- Prompt following is sensitive to style. Tag lists and prompts copied from other video models underperform. Rewrite them as flowing prose.
- Five seconds is short. Multi-shot generation exists in LTX 2.5, but two or more cuts in five seconds usually need shorter, clearer beats. Use a single continuous take unless the user explicitly asks for cuts.
- A five-second dialogue budget of about 10 to 12 words is an estimate derived from third-party guidance, not an official figure.
