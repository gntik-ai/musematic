import type { RubricDimension } from "@/types/evaluation";

export function validateWeightSum(dimensions: RubricDimension[]): {
  sum: number;
  isValid: boolean;
} {
  const sum = Number(
    dimensions.reduce((acc, dimension) => acc + dimension.weight, 0).toFixed(4),
  );
  return {
    sum,
    isValid: Math.abs(sum - 1) < 0.0001,
  };
}

export const RUBRIC_WEIGHT_VALIDATION_DEBOUNCE_MS = 50;
