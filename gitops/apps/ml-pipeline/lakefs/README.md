# LakeFS Helm Chart Deployment

export MY_DB_CONN="postgres://lakefs_user:password@host:5432/lakefs_db"
export MY_ENCRYPT="SuperSecretEncryptKey123"

helm upgrade --install . \
  --namespace lakefs \
  --create-namespace \
  --set mySecrets.dbConnectionString=$MY_DB_CONN \
  --set mySecrets.authEncryptSecret=$MY_ENCRYPT


