package com.wildfirespot.server.config;

import com.wildfirespot.server.gateway.HttpRobotGatewayClient;
import com.wildfirespot.server.gateway.MockRobotGatewayClient;
import com.wildfirespot.server.gateway.RobotGatewayClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/**
 * Spring configuration that selects and wires the active {@link RobotGatewayClient} bean.
 *
 * <p>The gateway mode is controlled by the {@code robot.gateway.mode} property:
 * <ul>
 *   <li>{@code http} — creates an {@link HttpRobotGatewayClient} backed by a
 *       {@link org.springframework.web.client.RestClient} pointing at the robot's
 *       FastAPI server ({@code robot.api.base-url}).</li>
 *   <li>any other value (default: {@code mock}) — uses the injected
 *       {@link com.wildfirespot.server.gateway.MockRobotGatewayClient}.</li>
 * </ul>
 */
@Configuration
public class RobotGatewayConfig {

    private static final Logger log = LoggerFactory.getLogger(RobotGatewayConfig.class);

    @Value("${robot.gateway.mode:mock}")
    private String gatewayMode;

    @Value("${robot.api.base-url:http://localhost:8000}")
    private String robotApiBaseUrl;

    @Value("${robot.api.connect-timeout-ms:3000}")
    private int connectTimeoutMs;

    @Value("${robot.api.read-timeout-ms:5000}")
    private int readTimeoutMs;

    @Bean
    @Primary
    public RobotGatewayClient robotGatewayClient(MockRobotGatewayClient mockRobotGatewayClient) {
        if ("http".equalsIgnoreCase(gatewayMode)) {
            log.info("RobotGateway mode=HTTP  base-url={}", robotApiBaseUrl);
            SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
            factory.setConnectTimeout(connectTimeoutMs);
            factory.setReadTimeout(readTimeoutMs);
            RestClient restClient = RestClient.builder()
                    .baseUrl(robotApiBaseUrl)
                    .requestFactory(factory)
                    .build();
            return new HttpRobotGatewayClient(restClient);
        }

        log.info("RobotGateway mode=MOCK");
        return mockRobotGatewayClient;
    }
}
