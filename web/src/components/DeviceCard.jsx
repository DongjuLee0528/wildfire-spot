import React from 'react';

function formatLastSeen(updatedAt) {
    if (!updatedAt) return 'Unknown';
    try {
        return new Date(updatedAt).toLocaleString();
    } catch {
        return 'Unknown';
    }
}

export default function DeviceCard({ device, selected, onSelect, onEdit, onDelete }) {
    return (
        <div className={`device-card${selected ? ' device-card-selected' : ''}`}>
            <div className="device-card-header">
                <span className="device-card-name">{device.name}</span>
                <span className="device-status device-status-unknown">UNKNOWN</span>
            </div>
            <div className="device-card-body">
                <div className="device-data-row">
                    <span className="device-label">Device ID</span>
                    <span className="device-value device-mono">{device.id}</span>
                </div>
                <div className="device-data-row">
                    <span className="device-label">Serial No.</span>
                    <span className="device-value device-mono">{device.serialNumber}</span>
                </div>
                {device.description && (
                    <div className="device-data-row">
                        <span className="device-label">Description</span>
                        <span className="device-value">{device.description}</span>
                    </div>
                )}
                <div className="device-data-row">
                    <span className="device-label">Last Seen</span>
                    <span className="device-value subtext">{formatLastSeen(device.updatedAt)}</span>
                </div>
            </div>
            <div className="device-card-actions">
                <button
                    className={`device-action-btn${selected ? ' device-action-btn-active' : ''}`}
                    onClick={onSelect}
                >
                    {selected ? 'Selected' : 'Select'}
                </button>
                <button className="device-action-btn" onClick={onEdit}>Edit</button>
                <button className="device-action-btn device-action-btn-danger" onClick={onDelete}>Remove</button>
            </div>
        </div>
    );
}
