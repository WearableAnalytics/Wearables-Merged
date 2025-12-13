# Define the Traefik Service configuratio
service:  
  # Configure the main web entrypoint service  
  web:  
    # Set the Kubernetes Service type to LoadBalancer  
    type: LoadBalancer   
  
    # 💡 Replace with the desired *static* IP for Traefik's LoadBalancer 
    loadBalancerIP: "194.94.4.68"  
  
    # Add OpenStack-specific annotations to the Service metadata  
    annotations:  
      # 💡 IMPORTANT: Replace the UUID/IP with your actual OpenStack values!

      # Subnetz-ID, in dem sich die Kubernetes Worker befinden (für die Load Balancer Members)  
      loadbalancer.openstack.org/member-subnet-id: "f36c7488-2bc4-4171-bc7d-25e0cca40c9e"

      # Netzwerk-ID für den Load Balancer VIP  
      loadbalancer.openstack.org/network-id: "a33fd200-d1c7-4e7a-b496-a0302db68560"

      # Subnetz-ID für den Load Balancer VIP  
      loadbalancer.openstack.org/subnet-id: "bd8ffe1c-2611-48b9-bace-280e64215bb5"
 
  # Configure the websecure entrypoint service (for HTTPS)  
  websecure:  
    # Set the Kubernetes Service type to LoadBalancer  
    type: LoadBalancer  
    
    # Use the same static IP for the secure listener  
    loadBalancerIP: "194.94.4.68"   
  
    # Apply the same OpenStack annotations  
    annotations:  
      # 💡 IMPORTANT: Replace the UUID/IP with your actual OpenStack values!  

      # Subnetz-ID, in dem sich die Kubernetes Worker befinden (für die Load Balancer Members)  
      loadbalancer.openstack.org/member-subnet-id: "f36c7488-2bc4-4171-bc7d-25e0cca40c9e"

      # Netzwerk-ID für den Load Balancer VIP  
      loadbalancer.openstack.org/network-id: "a33fd200-d1c7-4e7a-b496-a0302db68560"

      # Subnetz-ID für den Load Balancer VIP  
      loadbalancer.openstack.org/subnet-id: "bd8ffe1c-2611-48b9-bace-280e64215bb5"

# Recommended entrypoint configuration for standard web traffic  
ports:  
  web:  
    port: 80  
    hostPort: 80  
    expose: true  
    exposedPort: 80  
    protocol: TCP  
    # Optional: Enable HTTP to HTTPS redirection  
    # redirectTo: websecure  
  
  websecure:  
    port: 443  
    hostPort: 443  
    expose: true  
    exposedPort: 443  
    protocol: TCP  
    tls:  
      enabled: true

# Optional: Enable the Traefik Dashboard Service (useful for debugging)  
# Set to 'ClusterIP' or apply similar LoadBalancer settings if you want it externally exposed.  
# dashboard:  
#   enabled: true  
#   ingress:  
#     enabled: true