package com.wildfirespot.server.config;

import com.wildfirespot.server.auth.DeviceJwtAuthenticationFilter;
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
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final DeviceJwtAuthenticationFilter deviceJwtAuthenticationFilter;

    public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter,
                          DeviceJwtAuthenticationFilter deviceJwtAuthenticationFilter) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
        this.deviceJwtAuthenticationFilter = deviceJwtAuthenticationFilter;
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
                        // Public: login and signup
                        .requestMatchers(new AntPathRequestMatcher("/api/auth/login", "POST")).permitAll()
                        .requestMatchers(new AntPathRequestMatcher("/api/auth/signup", "POST")).permitAll()
                        // Public: Jetson device authentication
                        .requestMatchers(new AntPathRequestMatcher("/api/device-auth/login", "POST")).permitAll()
                        // Protected: current user info
                        .requestMatchers(new AntPathRequestMatcher("/api/auth/me", "GET")).authenticated()
                        // Protected: robot control and mode APIs
                        .requestMatchers(new AntPathRequestMatcher("/api/control/**")).authenticated()
                        .requestMatchers(new AntPathRequestMatcher("/api/mode/**")).authenticated()
                        // Protected: camera APIs
                        .requestMatchers(new AntPathRequestMatcher("/api/camera/control/**")).authenticated()
                        .requestMatchers(new AntPathRequestMatcher("/api/camera/status/**")).authenticated()
                        // Public: MJPEG stream is served via <img> which cannot send Authorization headers
                        .requestMatchers(new AntPathRequestMatcher("/api/camera/stream", "GET")).permitAll()
                        // Protected: robot, GPS, sensor, fire, mission, device APIs
                        .requestMatchers(new AntPathRequestMatcher("/api/robot/**")).authenticated()
                        .requestMatchers(new AntPathRequestMatcher("/api/gps/**")).authenticated()
                        .requestMatchers(new AntPathRequestMatcher("/api/sensors/**")).authenticated()
                        .requestMatchers(new AntPathRequestMatcher("/api/fire/**")).authenticated()
                        .requestMatchers(new AntPathRequestMatcher("/api/mission/**")).authenticated()
                        .requestMatchers(new AntPathRequestMatcher("/api/missions", null)).authenticated()
                        .requestMatchers(new AntPathRequestMatcher("/api/missions/**", null)).authenticated()
                        .requestMatchers(new AntPathRequestMatcher("/api/devices", null)).authenticated()
                        .requestMatchers(new AntPathRequestMatcher("/api/devices/**", null)).authenticated()
                        // Device endpoints: require DEVICE role (DEVICE JWT only)
                        .requestMatchers(new AntPathRequestMatcher("/api/device/heartbeat", "POST")).hasRole("DEVICE")
                        .requestMatchers(new AntPathRequestMatcher("/api/device/gps", "POST")).hasRole("DEVICE")
                        .requestMatchers(new AntPathRequestMatcher("/api/device/sensors", "POST")).hasRole("DEVICE")
                        .requestMatchers(new AntPathRequestMatcher("/api/device/fire-events", "POST")).hasRole("DEVICE")
                        // Public: status, health, logs
                        .requestMatchers(new AntPathRequestMatcher("/api/status", "GET")).permitAll()
                        .requestMatchers(new AntPathRequestMatcher("/api/health", "GET")).permitAll()
                        .requestMatchers(new AntPathRequestMatcher("/api/logs", "GET")).permitAll()
                        // Deny everything else not explicitly listed
                        .anyRequest().denyAll()
                )
                .addFilterBefore(deviceJwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class)
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
