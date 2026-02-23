using System;
using System.Collections.Generic;
using Shouldly;
using Xunit;
using Verge.Trading;

namespace Verge.Trading.Trading;

public class TradingStrategy_Tests
{
    [Fact]
    public void Should_Return_Multiple_Symbols_From_Json()
    {
        // Arrange
        var strategy = new TradingStrategy(Guid.NewGuid(), Guid.NewGuid(), "Test Strategy");
        strategy.SelectedCryptosJson = "[\"BTCUSDT\", \"ETHUSDT\", \"SOLUSDT\"]";

        // Act
        var symbols = strategy.GetSelectedCryptos();

        // Assert
        symbols.Count.ShouldBe(3);
        symbols.ShouldContain("BTCUSDT");
        symbols.ShouldContain("ETHUSDT");
        symbols.ShouldContain("SOLUSDT");
    }

    [Fact]
    public void Should_Return_Empty_List_If_Json_Is_Empty()
    {
        // Arrange
        var strategy = new TradingStrategy(Guid.NewGuid(), Guid.NewGuid(), "Test Strategy");
        strategy.SelectedCryptosJson = "";

        // Act
        var symbols = strategy.GetSelectedCryptos();

        // Assert
        symbols.ShouldBeEmpty();
    }
}
