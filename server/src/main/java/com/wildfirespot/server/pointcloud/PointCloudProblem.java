package com.wildfirespot.server.pointcloud;

import org.springframework.http.HttpStatus;

final class PointCloudProblem extends RuntimeException {
    final HttpStatus status;
    PointCloudProblem(HttpStatus status) { super(status.getReasonPhrase()); this.status = status; }
}
