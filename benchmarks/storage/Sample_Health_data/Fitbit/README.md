# LifeSnaps Fitbit dataset

Download and extract the [Kaggle dataset](https://www.kaggle.com/datasets/skywescar/lifesnaps-fitbit-dataset) into this directory with:

```bash
bash benchmarks/storage/Sample_Health_data/Fitbit/download.sh
```

The script requires [uv](https://docs.astral.sh/uv/), Python 3, and network access. It runs the Kaggle Python CLI in an isolated environment. The public dataset downloaded without authentication when this script was prepared; if Kaggle requires authentication, configure credentials according to the [Kaggle API documentation](https://github.com/Kaggle/kaggle-api#api-credentials).

The download is approximately 540 MiB compressed and 9.1 GiB extracted. The extracted `rais_anonymized` directory and temporary ZIP are ignored by Git. Running the script again downloads and extracts the dataset again and can overwrite existing files in that directory. Kaggle serves its current dataset version, which may change over time.

The script also retrieves `dataset-metadata.json` from Kaggle's public API, including the description and license (CC BY 4.0). This generated file is ignored by Git.
