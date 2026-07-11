# Local Model Directory

This folder is reserved for local model artifacts that are too large or too sensitive to commit.

Expected optional LayoutXLM path:

```text
model/
```

Required files for the fine-tuned LayoutXLM/LayoutLMv2 extractor:

- `config.json`
- `model.safetensors`
- `preprocessor_config.json`
- `sentencepiece.bpe.model`
- `special_tokens_map.json`
- `tokenizer_config.json`
- `tokenizer.json`
- `training_args.bin`

These files are ignored by Git. Share them through a model registry, release artifact, or private drive, then mount the folder when running Docker.
