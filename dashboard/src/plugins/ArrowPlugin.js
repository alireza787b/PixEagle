import ArrowComponent from '../components/ArrowComponent';

const arrowPlugin = {
  id: 'arrowPlugin',
  afterDatasetsDraw: (chart) => {
    const { ctx, scales: { x, y } } = chart;
    const datasetIndex = chart.data.datasets.findIndex(dataset => dataset.label === 'Velocity Vector');
    if (datasetIndex < 0 || !chart.isDatasetVisible(datasetIndex)) return;

    const velocityData = chart.data.datasets[datasetIndex].data;
    if (velocityData.length < 2) return;

    const start = velocityData[0];
    const end = velocityData[1];

    const startX = x.getPixelForValue(start.x);
    const startY = y.getPixelForValue(start.y);
    const endX = x.getPixelForValue(end.x);
    const endY = y.getPixelForValue(end.y);

    ArrowComponent({ ctx, startX, startY, endX, endY, color: 'rgba(0, 255, 0, 1)' });
  },
};

export default arrowPlugin;
