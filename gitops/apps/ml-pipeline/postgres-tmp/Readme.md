# This is a temporary Postgres deployment for testing LakeFS with ML Pipeline - replaece with Postgres when we got new volumes

export MY_DB_CONN="postgres://lakefs:lakefs_password@postgres-tmp-postgresql.postgres-tmp.svc.cluster.local:5432/lakefs"

helm upgrade --install postgres-tmp oci://registry-1.docker.io/bitnamicharts/postgresql \
  --version 18.2.0 \
  --namespace postgres-tmp \
  --create-namespace \
  --set auth.postgresPassword=mysecretpassword \
  --set auth.username=lakefs \
  --set auth.password=lakefs_password \
  --set auth.database=lakefs \
  --set primary.persistence.enabled=false


kubectl port-forward --namespace postgres-tmp svc/postgres-tmp-postgresql 5432:5432 & PGPASSWORD="$POSTGRES_PASSWORD" psql --host 127.0.0.1 -U lakefs -d lakefs -p 5432


### Testing
This spins up a temporary pod, attempts to login, prints the version, and deletes itself.

kubectl run -i --rm --tty debug-db-conn \
  --image=postgres:alpine \
  --restart=Never \
  --namespace postgres-tmp \
  --env="PGPASSWORD=lakefs_password" \
  --command -- psql -h postgres-tmp-postgresql -U lakefs -d lakefs -c "SELECT version();"


  You should see somethi like:

                                     version
------------------------------------------------------------------------------
 PostgreSQL 18.1 on x86_64-pc-linux-gnu, compiled by gcc (GCC) 12.2.0, 64-bit
(1 row)

pod "debug-db-conn" deleted from postgres-tmp namespace

test connection string

kubectl run db-connection-test \
  --image=postgres:alpine \
  --rm -it \
  --restart=Never \
  --namespace postgres-tmp \
  -- psql "postgres://lakefs:lakefs_password@postgres-tmp-postgresql.postgres-tmp.svc.cluster.local:5432/lakefs" \
  -c "\conninfo"

  you should see something like:

                              Connection Information
      Parameter       |                         Value
----------------------+--------------------------------------------------------
 Database             | lakefs
 Client User          | lakefs
 Host                 | postgres-tmp-postgresql.postgres-tmp.svc.cluster.local
 Host Address         | 10.240.25.91
 Server Port          | 5432
 Options              |
 Protocol Version     | 3.0
 Password Used        | true
 GSSAPI Authenticated | false
 Backend PID          | 2109
 SSL Connection       | false
 Superuser            | off
 Hot Standby          | off
(13 rows)

