package com.wildfirespot.server.device;

import com.wildfirespot.server.auth.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;
import jakarta.persistence.QueryHint;

import java.util.List;
import java.util.Optional;

public interface DeviceRepository extends JpaRepository<Device, String> {

    boolean existsBySerialNumber(String serialNumber);

    List<Device> findAllByOwner(User owner);

    Optional<Device> findBySerialNumber(String serialNumber);

    @Query("select d.owner.id from Device d where d.id = :deviceId")
    @QueryHints(@QueryHint(name = "jakarta.persistence.query.timeout", value = "1000"))
    Optional<String> findOwnerIdByDeviceId(@Param("deviceId") String deviceId);
}
