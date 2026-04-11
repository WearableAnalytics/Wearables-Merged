# TODO

- set up grafana properly --> can that be automated? where are the dashboards?
- storage classes may have to be changed --> currently cinder-csi but that may change depending on platform
- all images need to be built for the correct processor arch
- add somewhere that the setup was tested on minikube and mac (arm silicone)
- grafana needs to have 
- say designed for mac as local and minikube on remorte
- add commadn that forwards 80 to respective port, say port has to be configured dynamically, maybe add automation for that
```
echo "
rdr pass on lo0 inet proto tcp from any to 127.0.0.1 port 80 -> 127.0.0.1 port 12345
" | sudo pfctl -ef -
```
```
cat <<EOF | sudo pfctl -ef -
rdr pass on lo0 proto tcp from any to any port 80 -> 127.0.0.1 port 12345
EOF
```

if custom comfig save beforehand

revert with

```
sudo pfctl -ef /etc/pf.conf
```

and if not running before

```
sudo pfctl -d
```
- say need just or at least helpful
- add how to add dashboards
- add brevo key
- port changes in config