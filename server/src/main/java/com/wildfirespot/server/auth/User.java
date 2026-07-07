package com.wildfirespot.server.auth;

public record User(String username, String email, String name, String encodedPassword, String role) {}
