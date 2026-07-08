package com.wildfirespot.server.controller;

import com.wildfirespot.server.auth.JwtProvider;
import com.wildfirespot.server.auth.User;
import com.wildfirespot.server.auth.UserRepository;
import com.wildfirespot.server.dto.LoginRequest;
import com.wildfirespot.server.dto.LoginResponse;
import com.wildfirespot.server.dto.MeResponse;
import com.wildfirespot.server.dto.SignupRequest;
import com.wildfirespot.server.dto.SignupResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtProvider jwtProvider;

    public AuthController(UserRepository userRepository,
                          PasswordEncoder passwordEncoder,
                          JwtProvider jwtProvider) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtProvider = jwtProvider;
    }

    @PostMapping("/login")
    public ResponseEntity<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        User user = userRepository.findByEmail(request.email())
                .filter(u -> passwordEncoder.matches(request.password(), u.encodedPassword()))
                .orElseThrow(() -> new InvalidCredentialsException("Invalid email or password"));

        String token = jwtProvider.generate(user.username(), user.role());
        return ResponseEntity.ok(new LoginResponse(token));
    }

    @PostMapping("/signup")
    public ResponseEntity<SignupResponse> signup(@Valid @RequestBody SignupRequest request) {
        if (userRepository.existsByUsername(request.username())) {
            throw new SignupConflictException("Username already taken: " + request.username());
        }
        if (userRepository.existsByEmail(request.email())) {
            throw new SignupConflictException("Email already registered: " + request.email());
        }
        User user = new User(
                request.username(),
                request.email(),
                request.name(),
                passwordEncoder.encode(request.password()),
                "USER"
        );
        userRepository.save(user);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new SignupResponse(user.username(), user.email(), user.name()));
    }

    @GetMapping("/me")
    public ResponseEntity<MeResponse> me(@AuthenticationPrincipal String username) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new InvalidCredentialsException("User not found"));
        return ResponseEntity.ok(new MeResponse(user.username(), user.email(), user.name(), user.role()));
    }

    public static class InvalidCredentialsException extends RuntimeException {
        public InvalidCredentialsException(String message) {
            super(message);
        }
    }

    public static class SignupConflictException extends RuntimeException {
        public SignupConflictException(String message) {
            super(message);
        }
    }
}
