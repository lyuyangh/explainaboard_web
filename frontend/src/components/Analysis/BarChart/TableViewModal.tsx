import { Modal, Table } from "antd";
import React from "react";

const decimalPlaces = 3;

interface Props {
  title: string;
  visible: boolean;
  onClose: () => void;
  systemNames: string[];
  xValues: string[];
  yValues: number[][];
  xLabel?: string;
  yLabel?: string;
  yAxisMax?: number;
  confidenceScoresList: number[][][];
  numbersOfSamplesList: number[][];
}

export function TableViewModal({
  title,
  visible,
  onClose,
  systemNames,
  xLabel,
  yLabel,
  yAxisMax,
  xValues,
  yValues,
  confidenceScoresList,
  numbersOfSamplesList,
}: Props) {
  yAxisMax = yAxisMax === undefined ? 1 : yAxisMax;
  const formattedxAxisData = xValues.map((x) => x.replace("\n|\n", "-"));
  const trimmedConfidenceScores = confidenceScoresList.map(
    (confidenceScores) => {
      return confidenceScores.map(([lo, hi]) => {
        const loTrimmed = lo !== null ? Number(lo.toFixed(decimalPlaces)) : -1;
        const hiTrimmed = hi !== null ? Number(hi.toFixed(decimalPlaces)) : -1;
        return [loTrimmed, hiTrimmed];
      });
    }
  );
  const dataSrc = [];
  for (let i = 0; i < yValues[0].length; i++) {
    for (let sysIdx = 0; sysIdx < systemNames.length; sysIdx++) {
      dataSrc.push({
        xValue: formattedxAxisData[i],
        systemName: systemNames[sysIdx],
        yValue: yValues[sysIdx][i],
        confInterval: `[${trimmedConfidenceScores[sysIdx][i][0]}, ${trimmedConfidenceScores[sysIdx][i][1]}]`,
        sampleSize:
          numbersOfSamplesList[sysIdx][i] === -1
            ? "-"
            : numbersOfSamplesList[sysIdx][i],
      });
    }
  }

  const columns = [
    {
      title: "X Axis Value",
      key: "xValue",
      dataIndex: "xValue",
    },
    {
      title: "System Name",
      key: "systemName",
      dataIndex: "systemName",
    },
    {
      title: "Y Axis Value",
      key: "yValue",
      dataIndex: "yValue",
    },
    {
      title: "Confidence Interval",
      key: "confInterval",
      dataIndex: "confInterval",
    },
    {
      title: "Sample Size",
      key: "sampleSize",
      dataIndex: "sampleSize",
    },
  ];

  return (
    <Modal
      title={title}
      visible={visible}
      footer={null}
      onCancel={onClose}
      width="50%"
    >
      <Table pagination={false} dataSource={dataSrc} columns={columns} />
    </Modal>
  );
}
