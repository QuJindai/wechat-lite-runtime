FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The base image carries an unused Yarn repository whose retired signing key
# makes later Dev Container features fail during apt-get update.
RUN rm -f /etc/apt/sources.list.d/yarn.list
