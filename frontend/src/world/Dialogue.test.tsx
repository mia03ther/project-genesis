import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Dialogue } from "./Dialogue";

afterEach(cleanup);
describe("Dialogue controls", () => {
  it("advances with E, Enter and a touchable button, then repeats", () => {
    render(<Dialogue lines={["第一句", "第二句", "第三句"]} />);
    expect(screen.getByText("第一句")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "e" });
    expect(screen.getByText("第二句")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Enter" });
    expect(screen.getByText("第三句")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /再听一遍/ }));
    expect(screen.getByText("第一句")).toBeInTheDocument();
  });
  it("ignores key repeat and typing, preserving form controls", () => {
    render(
      <>
        <Dialogue lines={["第一句", "第二句"]} />
        <input aria-label="草稿" />
      </>,
    );
    fireEvent.keyDown(window, { key: "e", repeat: true });
    fireEvent.keyDown(screen.getByLabelText("草稿"), { key: "e" });
    expect(screen.getByText("第一句")).toBeInTheDocument();
  });
});
