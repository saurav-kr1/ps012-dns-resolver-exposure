# One small image that contains all the DNS programs used in the lab.
# iproute2-tc gives us `tc`, used to inject packet loss for the "lossy network" target (t08).
FROM alpine:3.20
RUN apk add --no-cache bind unbound dnsmasq bind-tools iproute2-tc
