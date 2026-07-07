package com.wildfirespot.server.auth;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public class UserRepository {

    private final User adminUser;

    public UserRepository(
            PasswordEncoder passwordEncoder,
            @Value("${auth.admin.username:admin}") String adminUsername,
            @Value("${auth.admin.password}") String adminPassword
    ) {
        this.adminUser = new User(adminUsername, passwordEncoder.encode(adminPassword), "ADMIN");
    }

    public Optional<User> findByUsername(String username) {
        if (adminUser.username().equals(username)) {
            return Optional.of(adminUser);
        }
        return Optional.empty();
    }
}
