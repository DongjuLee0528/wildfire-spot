package com.wildfirespot.server.auth;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Repository;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

@Repository
public class UserRepository {

    private final Map<String, User> byUsername = new ConcurrentHashMap<>();
    private final Map<String, User> byEmail = new ConcurrentHashMap<>();

    public UserRepository(
            PasswordEncoder passwordEncoder,
            @Value("${auth.admin.username:admin}") String adminUsername,
            @Value("${auth.admin.password}") String adminPassword
    ) {
        User admin = new User(adminUsername, adminUsername + "@wildfire.local", "Administrator",
                passwordEncoder.encode(adminPassword), "ADMIN");
        byUsername.put(admin.username(), admin);
        byEmail.put(admin.email(), admin);
    }

    public Optional<User> findByUsername(String username) {
        return Optional.ofNullable(byUsername.get(username));
    }

    public Optional<User> findByEmail(String email) {
        return Optional.ofNullable(byEmail.get(email));
    }

    public boolean existsByUsername(String username) {
        return byUsername.containsKey(username);
    }

    public boolean existsByEmail(String email) {
        return byEmail.containsKey(email);
    }

    public User save(User user) {
        byUsername.put(user.username(), user);
        byEmail.put(user.email(), user);
        return user;
    }
}
