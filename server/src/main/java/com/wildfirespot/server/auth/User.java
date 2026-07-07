package com.wildfirespot.server.auth;

public record User(String username, String encodedPassword, String role) {}
