import React from 'react';

const ArrowComponent = ({ ctx, startX, startY, endX, endY, color }) => {
  // Calculate the velocity components in the video frame coordinate system
  const velocityX = endX - startX;
  const velocityY = endY - startY;

  // Apply coordinate system transformation
  // Swap x and y components and negate both for 180-degree rotation
  const transformedVelocityX = -velocityY;
  const transformedVelocityY = -velocityX;

  // Calculate the new end coordinates after transformation
  const transformedEndX = startX + transformedVelocityX;
  const transformedEndY = startY + transformedVelocityY;

  // Calculate the angle of the arrow
  const angle = Math.atan2(transformedEndY - startY, transformedEndX - startX);
  const headLength = 10;

  // Draw the main line of the arrow
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(startX, startY);
  ctx.lineTo(transformedEndX, transformedEndY);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();

  // Draw the arrowhead
  ctx.beginPath();
  ctx.moveTo(transformedEndX, transformedEndY);
  ctx.lineTo(
    transformedEndX - headLength * Math.cos(angle - Math.PI / 6),
    transformedEndY - headLength * Math.sin(angle - Math.PI / 6)
  );
  ctx.lineTo(
    transformedEndX - headLength * Math.cos(angle + Math.PI / 6),
    transformedEndY - headLength * Math.sin(angle + Math.PI / 6)
  );
  ctx.lineTo(transformedEndX, transformedEndY);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.restore();
};

export default ArrowComponent;
