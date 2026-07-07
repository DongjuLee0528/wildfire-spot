package com.wildfirespot.server.config;

import com.wildfirespot.server.auth.JwtAuthenticationFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;

    public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        // Public: login only
                        .requestMatchers(HttpMethod.POST, "/api/auth/login").permitAll()
                        // Protected: current user info
                        .requestMatchers(HttpMethod.GET, "/api/auth/me").authenticated()
                        // Protected: robot control APIs
                        .requestMatchers("/api/control/**").authenticated()
                        .requestMatchers("/api/mode/**").authenticated()
                        .requestMatchers("/api/camera/control/**").authenticated()
                        .requestMatchers("/api/camera/status/**").authenticated()
                        .requestMatchers("/api/camera/stream/**").authenticated()
                        .requestMatchers("/api/robot/**").authenticated()
                        .requestMatchers("/api/gps/**").authenticated()
                        .requestMatchers("/api/sensors/**").authenticated()
                        .requestMatchers("/api/fire/**").authenticated()
                        .requestMatchers("/api/mission/**").authenticated()
                        .requestMatchers("/api/devices/**").authenticated()
                        // Public (read-only monitoring): status, health, logs
                        // These can be tightened later when the React login page is complete.
                        .requestMatchers(HttpMethod.GET, "/api/status", "/api/health", "/api/logs").permitAll()
                        // Deny everything else not explicitly listed
                        .anyRequest().denyAll()
                )
                .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOriginPatterns(List.of("*"));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(List.of("*"));
        config.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
